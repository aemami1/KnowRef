#!/usr/bin/python

import logging
import getpass
from itertools import chain
import progressbar
import ujson
import bz2
import nltk
import re
import HTMLParser
import psutil
import click
from joblib import Parallel, delayed
from nltk.tokenize import sent_tokenize, word_tokenize
from itertools import izip_longest, chain
import os
from util import g_pronouns_re, make_excl, grouper, g_connectives_re

g_excl_words = make_excl()

g_htmlparser = HTMLParser.HTMLParser()

def cleanup_line(line, mode):
    line = g_htmlparser.unescape(line)
    line = re.sub(r"\{\{\{?.*?\}\}\}?", "", line, 0, re.DOTALL)  # infoboxes
    line = re.sub(r"\{(.*?)\}", r"\1", line)   # stray markup?
    line = re.sub(r"<br>", r" ", line)         # found some stray ones of these
    line = re.sub(r'[^\x00-\x7F]', '', line)   # non-ascii chars
    line = re.sub(r"\(.*?\)", "", line, 0, re.DOTALL) # remove parentheses
    line = re.sub(r'\n=+References.*$', "", line) # remove references
    line = re.sub(r'^=.*$', "", line, 0, re.MULTILINE) # remove headings
    line = re.sub(r'^\*.*?$', "", line, 0, re.MULTILINE) # remove lists
    if line.count('"') > 0:
        # quotes are complicated constructs messing up sent_tokenize, and hopefully don't occur in WCD
        return []
    if re.match(r'.*\bart\.\s*\d+', line):
        # article (e.g. of the constitution), not correctly identified by sent_tokenize
        return []
    line = re.sub(r"\sM\.A\.\s", " MA ", line)   # sent_tokenize fails on this one

    # In much [[formal logic|formal]] work  -->  In much formal logic work
    line = re.sub(r"\[\s*\[(.*?)(?:\|[^\]]+?)?\]\s*\]", r"\1", line)

    # not sure where this is coming from
    line = re.sub(r":\d+", "", line, 0, re.MULTILINE)
    
    # more lines w/ junk we won't want to process
    line = re.sub(r"^[\d*=~#:].*?$", "", line, 0, re.MULTILINE)

    # collapse whitespace
    line = re.sub(r'[\s\n\r]+', " ", line)

    # backtracking for NP1...NP2..connective..NP[12] takes a lot of time
    # so we're much (~3x) faster when pre-filtering for the existence of connectives /first/
    sents = [s.strip() for s in sent_tokenize(line) if re.search(g_connectives_re, s)]

    # sanity check sentences
    sents = [s for s in sents 
            if len(s) > 0 
            and s[-1] in '.!?;'             # ends w/ punctuation
            and re.match(r'^[A-Z]', s)       # 1st word capitalized
            and s.count(" ") > 9             # enough words
            and s.count(" ") < 33            # too many
            and not re.search(r"[+=\d<]", s)  # no weird stuff
            ]

    # check reoccurrence pattern
    sents = [process_sentence(s, mode) for s in sents]

    return [s for s in sents if len(s) > 0]

def process_sentence(sent, mode):
    words = word_tokenize(sent)
    if len(words) > 30:
        return ""

    candidates = [word for word in words 
            if word not in g_excl_words 
            and re.match(r"^\w\w\w+$", word)]

    if len(candidates) == 0:
        return ""

    jcand = "|".join(candidates)
    if mode == 'noun':
        res = re.match(r'^(.*\b(%s)\b.+\b(%s))\b.*%s.*\b(\1|\2)\b'%(jcand,jcand,g_connectives_re), sent)
    elif mode == 'pronoun':
        res = re.match(r'^(.*\b(%s)\b.+\b(%s))\b.*%s.*%s'%(jcand,jcand,g_connectives_re,g_pronouns_re), sent)
    else:
        raise RuntimeError("Unknown mode `%s'" % mode)

    if res is None:
        return ""

    # make sure no pronoun before connective, hopefully makes sentence more "self-contained"
    if mode == 'pronoun':
        if re.match(r".*%s" % g_pronouns_re, res.group(1), re.IGNORECASE):
            return ""

    if res.group(2) == res.group(3):
        return ""

    return sent

def exclude_line_p(line):
    if line.startswith('<'):
        return True
    if line.count(" ") < 9:
        # heading?
        return True
    return False

def cleanup_bz2_file(filename, mode):
    infile = bz2.BZ2File(filename, "r", 4092)
    objs = ujson.loads(infile.read().decode('utf-8'))
    infile.close()
    articles = (obj['fullbody'] for obj in objs)
    articles = [cleanup_line(art, mode) for art in articles]
    sents = [s for s in chain(*articles)]
    return sents

def cleanup_json_file(filename, mode):
    with open(filename, "r") as f:
        objs = ujson.loads(f.read())
    articles = (obj['fullbody'] for obj in objs)
    articles = [cleanup_line(art, mode) for art in articles]
    sents = [s for s in chain(*articles)]
    return sents


@click.command()
@click.option('--mode', default='noun', type=click.Choice(['noun', 'pronoun']), help='Which regular expression to use for filtering')
@click.option('--n-jobs', default=1, type=int, help='number of threads to spawn')
@click.option('--chunk-size', default=120, type=int, help='number of work items per thread')
@click.argument('inputs_dir', type=click.Path(exists=True, file_okay=False), required=True)
@click.argument('output_filename', type=click.Path(exists=False, file_okay=False, dir_okay=False), required=True)
def main(mode, inputs_dir, output_filename, n_jobs, chunk_size):
    from glob import glob
    if os.path.exists(output_filename):
        user_in = ""
        while len(user_in)!=1 or user_in not in "aoe":
            user_in = raw_input("output filename `%s' already exists, append/overwrite/exit (aoe)?" % output_filename)
            if user_in == "e":
                print "Exiting."
                sys.exit(1)
            elif user_in == "o":
                print "Overwriting."
                output_file = open(output_filename, "w")
                with open("done_files.txt", "w") as f:
                    f.write("dummy")
                    pass
            elif user_in == "a":
                print "Appending."
                output_file = open(output_filename, "a")
    else:
        output_file = open(output_filename, "w")
    input_filenames = sorted(glob(os.path.join(inputs_dir, "*.json.bz2")))

    done_files = []
    if os.path.exists("done_files.txt"):
        with open("done_files.txt") as done_fd:
            done_files = [s.strip() for s in done_fd.readlines()]

    input_filenames = [f for f in input_filenames if f not in done_files]
    n_files = len(input_filenames)
    n_processed_files = 0

    widgets = [progressbar.ETA(), progressbar.Percentage()]
    pbar = progressbar.ProgressBar(widgets=widgets, maxval=n_files).start()
    logging.info("Processing %d / %d files", chunk_size, n_files)
    with Parallel(n_jobs=n_jobs) as parallel:
        for chunk in grouper(input_filenames, chunk_size):
            chunk = [f for f in chunk if f is not None]
            if len(chunk) == 0:
                continue
            try:
                sentences = parallel(delayed(cleanup_bz2_file)(filename, mode)
                        for filename in chunk if filename is not None)
            except EOFError:
                continue
            sentences = [l for l in chain(*sentences)]
            logging.info("Found %d sentences in [%s]", len(sentences), ", ".join(chunk))
            for sent in sentences:
                output_file.write(sent)
                output_file.write("\n")
            for f in chunk:
                done_files.append(f)
            with open("done_files.txt", "w") as f:
                f.write("\n".join(done_files))
            n_processed_files += len(chunk)
            pbar.update(n_processed_files)
    pbar.finish()



if __name__ == "__main__":
    logging.getLogger().setLevel(logging.INFO)
    main()

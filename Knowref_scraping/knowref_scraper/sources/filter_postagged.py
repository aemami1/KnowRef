import nltk
import re
import numpy as np
from nltk.tokenize import sent_tokenize, word_tokenize
from joblib import Parallel, delayed
import progressbar
from itertools import izip_longest, chain
from nltk import RegexpParser
from nltk import WordNetLemmatizer
import click



g_lemmatizer = WordNetLemmatizer()
g_patterns = """
    NP: {<DT>?<JJ>*<NN.*>+<IN>?<DT>?<JJ>*<NN.*>*}
        {<DT>?<JJ>*<NN.*><CC>*<DT>?<NN.*>+}
        """

g_connectives = set(",|;|or|since|but|because|although|even though|though|after|so|if|whether|until|where|when".split("|"))

def formatted_sent(chunked, cidx=[], print_tags=False):
    cidx = np.unique(cidx)
    L = []
    for idx, c in enumerate(chunked):
        if isinstance(c, tuple):
            if print_tags:
                L.append(c[0] + "_" + c[1])
            else:
                L.append(c[0])
        else:
            L.append(flatten(c))
        if idx in cidx:
            L[-1] = L[-1] + "*"
    return " ".join(L)

def flatten(tree):
    words = [w[0] for w in tree.leaves()]
    w = "_".join(words)
    return w

def remove_jj_and_flatten(tree):
    words = [g_lemmatizer.lemmatize(w[0]) for w in tree.leaves() if w[1] not in  ["JJ", "DT"]]
    return "_".join(words)

def get_jjs(tree):
    return "-".join([w[0] for w in tree.leaves() if w[1] in ["DT", "JJ"]]).lower()

def has_jj(tree):
    return any([w[1] == "JJ" for w in tree.leaves()])

def has_plural(tree):
    return any([re.match("N.*S", w[1]) for w in tree.leaves()])

def process_sentence(sent, parser, mode):
    word_pos = [word.split("_") for word in sent.split(" ") if word.count("_") == 1]
    word_pos = [tuple(pair) for pair in word_pos]

    res = parser.parse(word_pos)
    nps = [(idx, t, remove_jj_and_flatten(t)) for idx, t in enumerate(res) if isinstance(t, nltk.Tree)]
    if len(nps) > 5:
        return ["%s\n\tREJECTED: Too many noun phrases (%d)" % (" ".join(x[0] for x in word_pos), len(nps))]

    connectives = []
    for idx, r in enumerate(res):
        if isinstance(r, nltk.Tree):
            continue
        word, tag = r
        if word in g_connectives:
            connectives.append(idx)

    if len(connectives) == 0:
        return ["%s\n\tREJECTED: No connectives" % " ".join(x[0] for x in word_pos)]

    # collapse all consecutive occurrences of connectives, e.g. ", and though"
    connectives2 = [connectives[0]]
    last_c = connectives2[-1]
    for c in connectives[1:]:
        if c == last_c + 1:
            pass
        else:
            connectives2.append(c)
        last_c = c
    connectives = connectives2

    if len(connectives) > 2:
        # likely something like a list, don't include it.
        return ["%s\n\tREJECTED: too many connectives" % " ".join(x[0] for x in word_pos)]

    wsc_cands = []
    reject_reasons = []

    for cidx in connectives:
        nps_before_c = {s : idx for idx, t, s in nps if idx < cidx}
        if len(nps_before_c.keys()) < 2:
            continue
        nps_after_c = {s:idx for idx, t, s in nps if idx > cidx   # after connective
                and (not has_jj(res[idx])                         # no adjective
                    or any(get_jjs(res[v]) == get_jjs(res[idx])
                        for k, v in nps_before_c.items()))}       # same adjectives

        if len(set(nps_after_c.keys()).intersection(set(nps_before_c.keys()))) > 1:
            # multiple nps from before occur after c as well
            reject_reasons.append(">1 NP from before CON also occurs after")
            continue

        if mode == 'noun':
            for np_b, xb in nps_before_c.items():
                # compare to all nps before c
                for np_a, xa in nps_after_c.items():
                    if np_b == np_a:
                        # find another element from /before/, which is different from 
                        xb2 = None
                        for np_b2_, xb2_ in nps_before_c.items():
                            if np_b2_ == np_b or has_plural(res[xb2_]) != has_plural(res[xb]):
                                continue
                            xb2 = xb2_
                        if xb2 is None:
                            reject_reasons.append("no 2nd candidate before CON found for (%s, %s, %s)" % (np_b, res[cidx][0], np_a))
                            continue
                        wsc_cands.append(formatted_oneline(res, xb2, xa))
                    else:
                        reject_reasons.append("cmp failed (before/after): %s / %s" % (np_b, np_a))
        elif mode == 'pronoun':
            if len(set(nps_before_c.keys()).intersection(nps_after_c.keys())) > 0:
                # it is too easy if one of them appears again, since then the pronoun is the other one.
                reject_reasons.append("too easy")
                continue
            wsc_cands.append(formatted_oneline(res, nps_before_c.items()[0][1], nps_before_c.items()[1][1], mark_xa=False))
    return wsc_cands

def formatted_wsc(chunked, xb, xa):
    L = []
    for idx, c in enumerate(chunked):
        if isinstance(c, tuple):
            L.append(c[0])
        else:
            if idx == xa:
                L.append("[" + flatten(c) + "]")
            else:
                L.append(flatten(c))
    sentence = " ".join(L)
    cand1 = flatten(chunked[xa])
    cand0 = flatten(chunked[xb])
    print "%s\n	%s,%s\n\n" % (sentence, cand0, cand1)

def formatted_oneline(chunked, xb, xa, mark_xa=True):
    L = []
    for idx, c in enumerate(chunked):
        if isinstance(c, tuple):
            L.append(c[0])
        else:
            if idx == xa and mark_xa:
                L.append("[" + flatten(c) + "]")
            else:
                L.append(flatten(c))
    sentence = " ".join(L)
    cand1 = flatten(chunked[xa])
    cand0 = flatten(chunked[xb])
    return "%s|%s|%s" % (sentence, cand0, cand1)
    


def process_sentences(sents, mode):
    parser = RegexpParser(g_patterns)
    wsc_cands = [process_sentence(s, parser, mode) for s in sents if s is not None and len(s) > 0]
    wsc_cands = [l for l in chain(*wsc_cands)]
    return wsc_cands

def grouper(iterable, n, fillvalue=None):
    args = [iter(iterable)] * n
    return izip_longest(*args, fillvalue=fillvalue)


@click.command()
@click.argument('in_file', type=click.Path(exists=True, file_okay=True, dir_okay=False), required=True)
@click.argument('out_file', type=click.Path(exists=False, file_okay=False, dir_okay=False), required=True)
@click.option('--n-jobs', type=int, default=-1)
@click.option('--mode', type=click.Choice(['pronoun','noun']), default='noun')
def main(in_file, out_file, n_jobs, mode):
    outf = open(out_file, "w")
    with open(in_file, "r") as f:
        lines = f.readlines()

        widgets = [progressbar.ETA(), progressbar.Percentage()]
        pbar = progressbar.ProgressBar(widgets=widgets, maxval=len(lines)).start()
        n_lines = 0
        n_cand  = 0
        for big_chunk in grouper(lines, 8000):
            candidates = Parallel(n_jobs=n_jobs)(delayed(process_sentences)(chunk, mode) for chunk in grouper(big_chunk, 400))
            candidates = [l for l in chain(*candidates) if len(l) > 0 and "REJECTED" not in l]
            n_cand += len(candidates)
            print "Found %d candidates" % len(candidates)
            for c in candidates:
                outf.write(c)
                outf.write("\n")
            n_lines += len(big_chunk)
            pbar.update(min(n_lines, len(lines)))
            print "\nRatio cand/sents:", n_cand/float(n_lines)
        pbar.finish()

if __name__ == "__main__":
    main()

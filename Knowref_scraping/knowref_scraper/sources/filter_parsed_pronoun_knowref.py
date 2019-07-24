import re
import nltk
import networkx as nx
import untangle
from nltk.corpus import names
from itertools import chain
import random
import sexpdata
import sys
import os
import json
import click
from joblib import Parallel, delayed
from util import male_p, g_connectives_set, sexp2nx, g_pronouns_set, grouper

def contained(query, intervalset):
    """
    returns true if any element in intervalset is smaller than query and
    contained in it.
    """
    for i in intervalset:
        if query == i:
            continue
        if query[0] <= i[0] and i[1] <= query[1] and i[1]-i[0] < query[1]-query[0]:
            return True
    return False


class CoreNLPResult:
    def __init__(self, sent, mode):
        self.tokens = sent.tokens.token
        self.words = [t.word.cdata for t in self.tokens]
        sexp = sexpdata.loads(re.sub(r"(\w*\'+\w*)", r'"\1"', sent.parse.cdata.replace("\\", ":")), nil=None, true=None, false=None, line_comment=None)
        self.parsetree = sexp2nx(sexp)

        if len(self.words) < 5:
            self.ok = False
            return

        self.NPs = self.get_nps()
        self.connectives = self.get_connective_idxs(self.NPs)


        self.ok = False
        reason = ""
        for c in self.connectives:
            self.ok = False
            if not self.has_verb_after_connective(c):
                print "WARNING: no verb after connective in `%s'" % " ".join(self.words)
                self.ok = False
                return

            nps_before_connective = [np for np in self.NPs if np[1] <= c]
            nps_before_connective = [np for np in nps_before_connective if not contained(np, nps_before_connective)]

            if len(nps_before_connective) < 2:
                reason = "too few nouns before connective `%s'" % " ".join(self.words)
                continue
            if len(nps_before_connective) > 2:
                reason = "too many nouns before connective `%s'" % " ".join(self.words)
                continue

            self.cand0_idx = nps_before_connective[0]
            self.cand1_idx = nps_before_connective[1]

            pronouns = self.get_pronouns()
            if any(p for p in pronouns if p < c):
                reason = "pronoun before connective `%s'" % " ".join(self.words)
                continue

            if len(pronouns) == 0:
                reason = "no pronouns in `%s'" % " ".join(self.words)
                continue

            self.pronoun_token_idx = pronouns[0]

            self.cands_agree_on_type = self.agree_on_type(self.cand0_idx, self.cand1_idx)
            self.cands_agree_on_plural = self.agree_on_plural(self.cand0_idx, self.cand1_idx)
            self.cands_agree_on_gender = self.agree_on_gender(self.cand0_idx, self.cand1_idx)

            self.pronoun_is_plural = self.words[self.pronoun_token_idx] in ['they', 'them', 'those', 'these']
            self.pronoun_is_person = self.words[self.pronoun_token_idx] in ['he', 'she', 'her', 'his', 'hers', 'him']
            self.pronoun_is_male   = self.words[self.pronoun_token_idx] in ['he', 'him', 'his']

            self.connective_idx = c

        #Make sure everything is a person
        if self.pronoun_is_person and self.is_person(self.cand0_idx) and self.is_person(self.cand1_idx):    
            self.ok = True

        if not self.ok:
            return

        # not needed anymore, and prevents joblib from doing its job
        del self.parsetree
        del self.tokens

    def is_male(self, p):
        return male_p(self.tokens[p[-1]-1].word.cdata)
    def is_person(self, p):
        return self.tokens[p[-1]-1].NER.cdata == "PERSON"
    def is_plural(self, p):
        return self.tokens[p[-1]-1].POS.cdata[-1] == 'S'
    def agree_on_type(self, p0, p1):
        return self.is_person(p0) == self.is_person(p1)
    def agree_on_plural(self, p0, p1):
        return self.is_plural(p0) == self.is_plural(p1)
    def agree_on_gender(self, p0, p1):
        return self.is_male(p0) == self.is_male(p1)

    @property
    def pronoun_replaced(self):
        return " ".join(t for t in chain(self.words[:self.pronoun_token_idx],
            ["[%s]" % (" ".join(self.words[self.pronoun_token_idx:self.pronoun_token_idx+1]))],
            self.words[self.pronoun_token_idx+1:]))

    @property
    def original_sentence(self):
        return " ".join(t for t in self.words),

    @property
    def candidate0(self):
        return " ".join(t for t in self.words[self.cand0_idx[0] : self.cand0_idx[-1]]),

    @property
    def candidate1(self):
        return " ".join(t for t in self.words[self.cand1_idx[0] : self.cand1_idx[-1]]),

    @property
    def correct_candidate(self):
        c = self.cand0_idx if self.correct_candidate_idx == 0 else self.cand1_idx
        return " ".join(t for t in self.words[c[0] : c[-1]]),

    def write_yaml(self, fd):
        d = dict(
            original_sentence=self.original_sentence,
            sentence_with_pronoun=self.pronoun_replaced,

            candidate0=self.candidate0,
            candidate1=self.candidate1,
            correct_candidate=self.correct_candidate,
            correct_candidate_idx=self.correct_candidate_idx,

            is_pronoun_plural=self.pronoun_is_plural,
            is_pronoun_person=self.pronoun_is_person,
            is_pronoun_male=self.pronoun_is_male,

            is_agree_on_number=self.cands_agree_on_plural,
            is_agree_on_type=self.cands_agree_on_type,
            is_agree_on_gender=self.cands_agree_on_gender,
            )
        json.dump(d, fd)
        fd.write("\n")

    def get_connective_idxs(self, NPs):
        connectives = []
        for idx, token in enumerate(self.tokens):
            if token.word.cdata.strip() in g_connectives_set:
                connectives.append(idx)
        # remove consecutive connectives
        res = []
        last_i = -2
        for i in connectives:
            if i == last_i + 1:
                last_i = i
                continue
            res.append(i)
            last_i = i
        return [c for c in res if not self.is_inside_np(NPs, c)]

    def has_verb_after_connective(self, connective):
        for token in self.tokens[connective:]:
            if token.POS.cdata[0] == 'V':
                return True
        return False

    def is_inside_np(self, NPs, idx):
        """
        every NP is a pair [start, finish[. Iff idx is inside this range, return false.
        """
        for np in NPs:
            if np[0] <= idx and np[1] > idx:
                return True
        return False

    def get_pronouns(self):
        pronouns = [idx for idx, w in enumerate(self.words) if w in g_pronouns_set]
        return pronouns

    def get_nps(self):
        """
        returns a list of pairs, [p0, pn[, of indices into self.words.
        """

        # determine all leaf ids in the parse tree which refer to a noun
        nouns = []
        for node_id in self.parsetree.nodes():
            node = self.parsetree.node[node_id]
            if not node['is_leaf']:
                continue
            leaf_idx = node['left_leaf_idx']
            if leaf_idx >= len(self.tokens):
                continue
            self.words[leaf_idx] == node['label']
            is_noun = self.tokens[leaf_idx].POS.cdata[0] == 'N'
            if is_noun:
                nouns.append(node_id)

        NPs = set()
        for noun in nouns:
            NPs.add(self.get_np_for_idx(noun))
        return NPs

    def get_np_for_idx(self, idx):
        child = idx

        while True:
            parent = list(self.parsetree.in_edges(child))[0][0]
            if self.parsetree.node[parent]['label'][0] == 'N':
                child = parent
            else:
                break
        tokens = (self.parsetree.node[child]['left_leaf_idx'],
                self.parsetree.node[child]['right_leaf_idx'])
        return tokens



    @property
    def postagged(self):
        return " ".join(t.word.cdata + "_" + t.POS.cdata for t in self.tokens)

    def postagged_words(self, idx):
        tokens = [self.tokens[i] for i in idx]
        return " ".join(t.word.cdata + "_" + t.POS.cdata for t in tokens)

    def draw(self, g=None):
        if g is None:
            g = self.depgraph
        import matplotlib.pyplot as plt
        pos = nx.graphviz_layout(g)
        nx.draw_networkx(g, pos=pos, with_labels=True, labels={k:v['label'] for k, v in g.nodes(data=True)})
        try:
            nx.draw_networkx_edge_labels(g, pos=pos, edge_labels={(src, dst):g[src][dst]['label'] for (src,dst) in g.edges()})
        except:
            pass
        plt.show()

        
def parse_files(chunk, mode):
    results = []
    for filename in chunk:
        if filename is None:
            continue
        obj = untangle.parse(filename)
        sents = [CoreNLPResult(s, mode) for s in obj.root.document.sentences.sentence]
        sents = [s for s in sents if s.ok]
        results.extend(sents)
    return results

def parse_xml_file(filename_glob, output_filename, mode, n_jobs):
    data = {}

    from glob import glob
    filenames = sorted(glob(filename_glob))
    n_parsed = 0
    sents = []
    if os.path.exists(output_filename):
        print "ERROR: output filename already exists"
        sys.exit(1)
    outfile = open(output_filename, "w")
    n_ok = 0
    print "Number of files: ", len(filenames)
    with Parallel(n_jobs=n_jobs, verbose=4) as parallel:
        for chunk in grouper(filenames, 10*n_jobs):
            try:
                sents = parallel(delayed(parse_files)([fn], mode) for fn in chunk)
        
                for sent in chain(*sents):
                    if sent.ok:
                            sent.write_yaml(outfile)
                            n_ok += 1
                    n_parsed += 1
                del sents

            except: 
                print "ERROR"

    print "Total OK sentences:", n_ok
    print "Frac of OK sentences:", n_ok / float(n_parsed)


@click.command()
@click.argument('input_glob', type=str, required=True)
@click.argument('output_filename', type=str, required=True)
@click.option('--mode', type=click.Choice(['pronoun','noun']), default='noun')
@click.option('--n-jobs', type=int, default=1)
def main(input_glob, output_filename, mode,n_jobs):
    parse_xml_file(input_glob, output_filename, mode, n_jobs)
    

if __name__ == "__main__":
    main()

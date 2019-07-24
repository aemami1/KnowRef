import nltk
import sexpdata
import networkx as nx
from itertools import izip_longest
import random
from nltk.corpus import names

g_pronouns_re  = r"\b(he|she|it|they|him|her|them|their|his|hers|these|those)\b"
g_pronouns_set = set(r"he|she|it|they|him|her|them|their|his|hers|these|those".split("|"))
g_connectives_set = set(",|;|or|since|but|because|although|even though|though|after|so|if|whether|until|where|when".split("|"))
g_connectives_re = r'\b(%s)\b' % "|".join(g_connectives_set)

def make_excl():
    excl_words = set()
    tb = nltk.corpus.treebank
    for word, tag in tb.tagged_words():
        if tag[0] != 'N':
            excl_words.add(word)
    return excl_words

def grouper(iterable, n, fillvalue=None):
    args = [iter(iterable)] * n
    return izip_longest(*args, fillvalue=fillvalue)


def sexp2nx(parsetree):
    return sexp2nx_(parsetree)[0]

def sexp2nx_(parsetree, g=None, parent=None, leaf_idx=0, node_idx=0):
    # convert a s-expression to a NetworkX graph
    if g is None:
        g = nx.DiGraph()
    
    if isinstance(parsetree, list):
        label = parsetree[0]
        if isinstance(parsetree[0], sexpdata.Symbol):
            label = parsetree[0].value()
        g.add_node(node_idx, label=label, is_leaf=False, left_leaf_idx=leaf_idx, right_leaf_idx=leaf_idx+1)
        if parent is not None:
            g.add_edge(parent, node_idx)

        head_node = node_idx
        node_idx += 1

        for idx, node in enumerate(parsetree[1:]):
            _, leaf_idx, node_idx = sexp2nx_(node, g, head_node, leaf_idx, node_idx)
        g.node[head_node]['right_leaf_idx'] = leaf_idx  # last index is this minus one!
    else:
        # we're given an instance of 'Symbol'
        label = parsetree
        if isinstance(parsetree, sexpdata.Symbol):
            label = parsetree.value()
        g.add_node(node_idx, label=label, is_leaf=True, leaf_idx=leaf_idx,
                left_leaf_idx=leaf_idx, right_leaf_idx=leaf_idx+1)
        g.add_edge(parent, node_idx)

        node_idx += 1
        leaf_idx += 1

    return g, leaf_idx, node_idx

g_male_names = names.words('male.txt')
g_female_names = names.words('female.txt')

def gender_features(word):
    return {'last_letter': word[-1]}


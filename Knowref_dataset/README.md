## [The KnowRef Coreference Corpus]


The dataset is generated using Reddit comments (2006-2018), 2018 English Wikipedia, and Opensubtitles.


## DATASET DESCRIPTION ##

The KnowRef dataset release comprises of one .json file, with 10 keys per instance. The keys other than "sentence_with_pronoun:, "candidate1", "candidate0", "correct_candidate", and "original_sentence" were heuristically determined and used during our filtering procedures and not used at all during training but we leave it there for transparency. As for the import keys:

"sentence_with_pronoun" provides the sentence with the target pronoun in square parentheses.

"candidate1" and "candidate2" provide the candidates one of which refers to the target pronoun correctly.

"correct_candidate" is the correct referring candidate

"original_sentence" is the original sentence as pulled from the source.

The files are:

Test 1,269 sentences, to be used for evaluation

Development 5,219 sentences, may be used for model development
Validation 2,236 sentences, may be used for parameter tuning

*NOTE* that for legal reasons, we are able to only provide the post ID and comment ID for the development and validation instances corresponding to the reddit post/comment which includes the sentence instance that can be extracted using the scraping code we have provided. 

The format for these in the excel file, for example in the dev tab, is ------ corresponding to the post ID, followed by ------- corresponding to the comment ID (which may be "Null", meaning the sentence is located in the post itself), the pronoun gender, following by the candidates in the sentence (which are names that were used to automatically replace the original antecedents) as well as the guessed label (guessed according to which original antecedent matched the gender of the pronoun)

The posts/comments can be retrieved using https://github.com/microsoft/dstc8-reddit-corpus.


## [Dataset Pre-processing]

## Generated Dataset location ##
The test dataset is in an orphan branch of this project, called =Knowref_dataset=.

## Idea ##

Produce a dataset with similar properties as winograd schema sentences.

We find sentences which have two noun phrases in them, one of which is referred to later. 

The resulting dataset may contain sentences where the original target of the reference cannot be determined anymore if for the noun phrases that are persons, they are changed to names of the same gender as the pronoun.

E.g. we pull "Kevin yelled at Melissa because he was angry" which can later be changed automatically to "Kevin yelled at Jim because he was angry"--Thus they become WSC-style, common sense requiring sentences.

## Procedure ##

General remark: Most of the scripts use [[https://pypi.python.org/pypi/joblib][joblib]] to parallelize processing. For
debugging, it is advisable to set it to one. To speed up processing, set the
**--n_jobs** parameter to a value larger than one.

All steps are also accessible from **pipeline.bash**.

1. Download the source text, e.g. 2016 wikipedia dump
2. Use **wikidump.py** to process the 12GB (bzip2’ed) to a cleaned up 4.3GB (bzip2’ed)
3. Use **split_sentences.py** to remove paragraphs containing lists etc., split
   sentences, and filter sentences which contain numbers, symbols, etc.
   Usage:
   
   ```
   python split_sentences.py --mode {mode} {inputs_dir} {output_filename}
   ```

   where **inputs_dir** is the directory where **WikiExtractor.py** stored the
   pre-processed wikipedia dump and **output_filename** is a filename of your
   choosing. 

   The sentences are searched for a regular expression containing a simplified
   form of the Winograd Schema pattern, e.g.

   =Noun1…Noun2…connective…Noun[1 or 2]=  (mode =noun=)
   =Noun1…Noun2…connective…pronoun=  (mode =pronoun=)

   In both cases, there shouldn’t be a pronoun before the connective, to ensure
   we don’t reference a sentence from before the current one.

   We don’t want to parse the sentence for nouns yet, instead we just remove all
   words from the sentence which occur in Penn Treebank as non-nouns, and
   compile the leftover words into the candidates-regex.

   The process takes about 20 minutes using around 32 cores of =rohan=. Use
   [[http://linux.die.net/man/1/nice][=nice=]] to reduce effects on other users.

4. Run the [[http://nlp.stanford.edu/software/tagger.shtml#Download][Stanford POS tagger]] on the resulting set. Download it, unzip it, and use
   ```
   java -cp "*:lib/*" edu.stanford.nlp.tagger.maxent.MaxentTagger -model models/english-left3words-distsim.tagger -textFile {input_file} -outputFormat slashTags -outputFile {output_file}
   ```
   This should be done after about 10-15 minutes. There is an =-nthreads= option
   in case this is too slow.

5. The POS tags provide further information about the candidate noun phrases,
   e.g., whether there actually are nouns, whether they agree in Number, whether
   there are too many other confounding NPs, whether they differ in adjectives
   (e.g. “The red car … but the green car…” would not be a repetition of “car”)

   This is done by **filter_postagged.py**, Usage:
   ```
   $ python filter_postagged.py [--n-jobs {N}] --mode {noun|pronoun} {postagger output file} {output_filename}
   ```
    
   This takes about 20 minutes.

6. Run the [[https://stanfordnlp.github.io/CoreNLP/][CoreNLP Parser]] on the resulting set. This seems to work fastest
   (judging by CPU usage) if the input is first split into multiple files. We
   can use the **split** command to do this for us, but before, we need to remove
   information about the candidates and the pronoun substitution position from
   the output of the last script:
   ```
   $ perl -ne '/^(.*?)\|/; $_=$1; s/[_\[\]]/ /g; print "$_\n"' < {filter_postagged output} > wsc_inputs.txt
   $ split -l 100 wsc_inputs.txt sentences/sents
   $ find sentences > filelist.txt
   $ java -cp "*" -Xmx6g edu.stanford.nlp.pipeline.StanfordCoreNLP -annotators tokenize,ssplit,pos,lemma,ner,parse -threads 32 -filelist filelist.txt
   ```

7. Final parsing step. CoreNLP parser. It messes up in a few cases where CoreNLP and nltk disagree about sentence splitting.
   ```
      $ python filter_parsed_pronoun_knowref.py "{corenlp glob}" {output filename}
   ```
   The glob is something like **stanford-corenlp-version/sents*.out**.
   This script:
   - finds the candidates, connective, and pronouns and filters through only sentences with personned noun phrases, the connective and a pronoun.


**Important Notes**:

Our test dataset is a result of the above scraping scripts applied to the wikipedia and opensubtitles corpora. The final result (the dataset itself) is provided in the orphan branch Knowref_dataset/test

Our training dataset is a result of the above scraping scripts applied to Reddit posts and comments. Due to legal reasons, we are only able to provide the post IDs and the comment IDs corresponding to the posts/comments from which the training sentences were scraped. In order to retrieve them, you can apply the scripts above on a bzip2'ed collection of the posts/comments that you may retrieve using the post IDs and the comment IDs (this can be done with the Reddit generation code publically accessible here: https://github.com/microsoft/dstc8-reddit-corpus).

**NLTK Libaries** 

Some of the python files require NLTK libraries to be downloaded, which can be done using nltk.download('____') within a python console. The two libraries are 'treebank' and 'names'.



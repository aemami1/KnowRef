MODE=${MODE:-pronoun}
ID=${ID:-owndump}
ACTION=$1

if [ "$ACTION" == "split" ] ; then
    PYTHONPATH=`pwd` nice -5 python knowref_scraper/sources/split_sentences.py --mode $MODE enwiki3 data/wp_${MODE}_${ID}.txt --n-jobs -1 --chunk-size 120   #For wikipedia
    #PYTHONPATH=`pwd` nice -5 python knowref_scraper/sources/split_sentences.py --mode $MODE opensubtitles data/wp_${MODE}_${ID}.txt --n-jobs -1 --chunk-size 120 -- for opensubtitles
    #PYTHONPATH=`pwd` nice -5 python knowref_scraper/sources/split_sentences.py --mode $MODE reddit data/wp_${MODE}_${ID}.txt --n-jobs -1 --chunk-size 120 -- for reddit
fi

if [ "$ACTION" == "postag" ] ; then
    cd stanford-postagger-full-2018-02-27
    nice -10 java -cp "*:lib/*" edu.stanford.nlp.tagger.maxent.MaxentTagger -model models/english-left3words-distsim.tagger -textFile ../data/wp_${MODE}_${ID}.txt -outputFormat slashTags -outputFile ../data/wp_${MODE}_${ID}_pos.txt -nthreads 24
    cd ..
fi

if [ "$ACTION" == "postag_filter" ] ; then
    PYTHONPATH=`pwd` nice -5 python knowref_scraper/sources/filter_postagged.py data/wp_${MODE}_${ID}_pos.txt data/wp_${MODE}_${ID}_pos_filtered.txt --mode ${MODE} --n-jobs -1
fi

if [ "$ACTION" == "corenlp" ] ; then
    cd stanford-corenlp-full-2018-02-27
    mkdir -p sentences
    perl -ne '/^(.*?)\|/; $_=$1; s/[_\[\]]/ /g; print "$_\n"' ../data/wp_${MODE}_${ID}_pos_filtered.txt > wp_${MODE}_${ID}_inputs.txt
    split -l 100 wp_${MODE}_${ID}_inputs.txt sentences/wp_${MODE}_${ID}_
    find sentences | grep wp_${MODE}_${ID}_ > wp_${MODE}_${ID}_filelist.txt
    nice -10 java -cp "*" -Xmx3g edu.stanford.nlp.pipeline.StanfordCoreNLP -annotators tokenize,ssplit,pos,lemma,ner,parse -threads 8 -filelist wp_${MODE}_${ID}_filelist.txt
    cd ..
fi

if [ "$ACTION" == "final" ] ; then
    if [ "$MODE" == "pronoun" ] ; then
        PYTHONPATH=`pwd`  nice -10 python  knowref_scraper/sources/filter_parsed_pronoun_knowref.py  "stanford-corenlp-full-2018-02-27/wp_${MODE}_${ID}_*.xml" data/wp_${MODE}_${ID}_final.json --n-jobs 16
fi

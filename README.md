# KnowRef Coreference Corpus
# AUTHORS: Ali Emami, Paul Trichelair, Adam Trischler, Kaheer Suleman, Hannes Schulz, and Jackie Cheung

# Abstract:

We introduce a new benchmark for coreference resolution and NLI, Knowref, that targets common-sense understanding and world knowledge. Previous coreference resolution tasks can largely be solved by exploiting the number and gender of the antecedents, or have been handcrafted and do not reflect the diversity of naturally occurring text. With these limitations in mind, we present a corpus of over 8,000 annotated text passages with ambiguous pronominal anaphora. These instances are both challenging and realistic. We show that various coreference systems, whether rule-based, feature-rich, or neural, perform significantly worse on the task than humans, who display high inter-annotator agreement. To explain this performance gap, we show empirically that state-of-the art models often fail to capture context, instead relying on the gender or number of candidate antecedents to make a decision. We then use problem-specific insights to propose a data-augmentation trick called "antecedent switching" to alleviate this tendency in models. Finally, we show that antecedent switching yields promising results on other tasks as well: we use it to achieve state-of-the-art results on the GAP coreference task.

# Reproduce Results

=Knowref_dataset= contains the test data and information required to generate the training data (as well a Readme with more details). 

=Knowref_scraping= contains code for the scraping of the corpus from the text sources (as well as a Readme with reproduce instructions)

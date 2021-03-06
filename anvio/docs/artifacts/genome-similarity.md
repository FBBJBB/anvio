This is the output of %(anvi-compute-genome-similarity)s (which describes the level of similarity between all of the input genomes) or %(anvi-script-compute-ani-for-fasta)s (which describes the level of similarity between contigs in a fasta file). 

{:.notice}
The output of %(anvi-compute-genome-similarity)s will only be in this structure if you did not input a %(pan-db)s. Otherwise, the data will be put directly into the additional data tables of the %(pan-db)s. The same is true of %(anvi-script-compute-ani-for-fasta)s. 

This is a directory (named by the user) that contains both a %(dendrogram)s (NEWICK-tree) and a matrix of the similarity scores between each pair for a variety of metrics dependent on the program that you used to run %(anvi-compute-genome-similarity)s or %(anvi-script-compute-ani-for-fasta)s .

For example, if you used `pyANI`'s `ANIb` (the default program), the output directory will contain the following twelve files. These are directly created from the heatmaps generated by PyANI, just converted into matrices and newick files: 

-`ANIb_alignment_coverage.newick` and `ANIb_alignment_coverage.txt`: contains the percent coverage (for query and subject)

-`ANIb_percentage_identity.newick` and `ANIb_percentage_identity.txt`: contains the percent identity

-`ANIb_full_percentage_identity.newick` and `ANIb_full_percentage_identity.txt`: contains the percent identity in the context of the length of the entire query and subject sequences (not just the aligned segment)

-`ANIb_alignment_lengths.newick` and `ANIb_alignment_lengths.txt`: contians the total aligned lengths 

-`ANIb_similarity_errors.newick` and `ANIb_similarity_errors.txt`: contains similarity errors (total number of mismatches, not including indels)

-`ANIb_hadamard.newick` and `ANIb_hadamard.txt`: contians the hadamard matrix (dot product of identity and coverage matrices)


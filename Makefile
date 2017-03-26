
# Running the two tasks for all in parallel might wreak havoc.
.NOTPARALLEL:
.PHONY: all update

all: update MANUAL.pdf

# Yay! Plumbing commands!
update:
	git checkout master -- MANUAL.md
	git update-ref HEAD $$(git commit-tree \
	    -m "Import changes from 'master'" \
	    -p $$(git rev-parse HEAD) -p $$(git rev-parse master) \
	    $$(git write-tree))

MANUAL.pdf: MANUAL.md
	pandoc $< --toc --filter ./headings.py -V geometry=margin=1.5in -o $@

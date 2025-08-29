# Makefile for building Sphinx docs and Python package

.PHONY: all docs build clean

# Build everything: docs + package
all: docs build

# Build Sphinx documentation
docs:
	sphinx-build -b html doc/ doc/_build/html

# Build the Python package (wheel and source)
build:
	python -m build

# Clean build artifacts
clean:
	rm -rf build/ dist/ *.egg-info doc/_build

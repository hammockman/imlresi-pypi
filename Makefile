build: src/imlresi/*.py
	python3 -m build

upload: build
	python3 -m twine upload --repository testpypi --verbose dist/*

upload-real: clean build
	python3 -m twine upload --repository pypi --verbose dist/*

test: build
	tox

clean:
	rm -rf dist/*

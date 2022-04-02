build: src/imlresi/*.py
	python3 -m build

upload:
	python3 -m twine upload --repository testpypi --verbose dist/*

upload-real:
	python3 -m twine upload --repository pypi --verbose dist/*

test: build
	tox

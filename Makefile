build: src/imlresi/*.py
	python3 -m build

upload:
	python3 -m twine upload --repository testpypi --verbose dist/*

test: build
	tox

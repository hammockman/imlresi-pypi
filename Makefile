build: src/imlresi/*.py
	python3 -m build

upload: build
	python3 -m twine upload --repository testpypi --verbose dist/*

upload-real: clean build
	python3 -m twine upload --repository pypi --verbose dist/* && \
	(VERSION=$$(awk -F'"' '/^version\s*=\s*/ {print $$2}' pyproject.toml); \
	NEXT_VERSION=$$(echo $$VERSION | awk -F. '{print $$1"."$$2"."$$3+1}'); \
	sed -i "s/version\s*=\s*\"$$VERSION\"/version = \"$$NEXT_VERSION\"/" pyproject.toml && \
	echo "Bumped version in pyproject.toml: $$VERSION -> $$NEXT_VERSION")

test: build
	tox

clean:
	rm -rf dist/*

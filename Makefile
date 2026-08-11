build: src/imlresi/*.py
	python3 -m build

upload: build
	python3 -m twine upload --repository testpypi --verbose dist/*

upload-real: clean build
	python3 -m twine upload --repository pypi --verbose dist/* && \
	(VERSION=$$(awk -F'"' '/^version\s*=\s*/ {print $$2}' pyproject.toml); \
	NEXT_VERSION=$$(echo $$VERSION | awk -F. '{print $$1"."$$2"."$$3+1}'); \
	sed -i "s/version\s*=\s*\"$$VERSION\"/version = \"$$NEXT_VERSION\"/" pyproject.toml && \
	echo "Bumped version in pyproject.toml: $$VERSION -> $$NEXT_VERSION"; \
	HQP_DIR="../Dropbox/Projects/2025_HQP_ResiPipelineRebuild/Fabric/hqp"; \
	HQP_TOML="$$HQP_DIR/pyproject.toml"; \
	if [ -f "$$HQP_TOML" ]; then \
		sed -i -E "s/\"imlresi>=[0-9.]+\"/\"imlresi>=$$VERSION\"/" "$$HQP_TOML" && \
		echo "Updated $$HQP_TOML with imlresi>=$$VERSION" && \
		(cd "$$HQP_DIR" && python3 -m build) && \
		echo "Rebuilt hqp wheel" || echo "Warning: Failed to update $$HQP_TOML or rebuild wheel"; \
	else \
		echo "Warning: Could not find $$HQP_TOML"; \
	fi)

test: build
	tox

clean:
	rm -rf dist/*

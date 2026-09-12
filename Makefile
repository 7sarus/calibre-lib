PLUGIN_NAME = libgen_downloader.zip
SOURCES = __init__.py ui.py dialog.py scraper.py config.py plugin-import-name-libgen_store.txt images/icon.png

.PHONY: all build install uninstall test clean release release-beta

all: build

build: $(PLUGIN_NAME)

$(PLUGIN_NAME): $(SOURCES)
	@echo "Packaging $(PLUGIN_NAME)..."
	@rm -f $(PLUGIN_NAME)
	@zip -q -r $(PLUGIN_NAME) $(SOURCES)
	@echo "Successfully created $(PLUGIN_NAME)"

install: build
	@echo "Installing $(PLUGIN_NAME) into Calibre..."
	calibre-customize -a $(PLUGIN_NAME)
	@echo "Plugin installed successfully. Restart Calibre to take effect."

uninstall:
	@echo "Removing LibGen Downloader plugin from Calibre..."
	calibre-customize -r "LibGen Downloader" || true
	calibre-customize -r "LibGen" || true

test: install
	@echo "Testing LibGen plugin modules and UI instantiation..."
	calibre-debug test_plugin.py

clean:
	rm -f $(PLUGIN_NAME) *.pyc libgen_store.zip
	rm -rf __pycache__

release-beta: build
	@if [ -z "$(TAG)" ]; then echo "Error: TAG is required (e.g. make release-beta TAG=v1.10b)"; exit 1; fi
	@echo "Creating and publishing beta release hook for $(TAG)..."
	git tag -f -a $(TAG) -m "$(TAG) Beta Release"
	git push origin $(TAG)
	gh release create $(TAG) $(PLUGIN_NAME) --title "$(TAG) (Beta)" --prerelease --generate-notes || gh release upload $(TAG) $(PLUGIN_NAME) --clobber
	@echo "✓ Beta release $(TAG) published successfully."

release: build
	@if [ -z "$(TAG)" ]; then echo "Error: TAG is required (e.g. make release TAG=v1.1.0)"; exit 1; fi
	@echo "Creating and publishing official release hook for $(TAG)..."
	git tag -f -a $(TAG) -m "$(TAG) Official Release"
	git push origin $(TAG)
	gh release create $(TAG) $(PLUGIN_NAME) --title "$(TAG)" --generate-notes || gh release upload $(TAG) $(PLUGIN_NAME) --clobber
	@echo "✓ Official release $(TAG) published successfully."

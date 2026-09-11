PLUGIN_NAME = libgen_downloader_release.zip
SOURCES = __init__.py ui.py dialog.py scraper.py config.py plugin-import-name-libgen_store.txt images/icon.png

.PHONY: all build install uninstall test clean

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

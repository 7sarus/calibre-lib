PLUGIN_NAME = libgen_store.zip
SOURCES = __init__.py store.py scraper.py config.py plugin-import-name-libgen_store.txt

.PHONY: all build install uninstall test clean

all: build

build: $(PLUGIN_NAME)

$(PLUGIN_NAME): $(SOURCES)
	@echo "Packaging $(PLUGIN_NAME)..."
	@rm -f $(PLUGIN_NAME)
	@zip -q $(PLUGIN_NAME) $(SOURCES)
	@echo "Successfully created $(PLUGIN_NAME)"

install: build
	@echo "Installing $(PLUGIN_NAME) into Calibre..."
	calibre-customize -a $(PLUGIN_NAME)
	@echo "Plugin installed successfully. Restart Calibre to take effect."

uninstall:
	@echo "Removing LibGen plugin from Calibre..."
	calibre-customize -r "LibGen" || true

test: install
	@echo "Testing LibGen store search in Calibre..."
	calibre-debug test_plugin.py

clean:
	rm -f $(PLUGIN_NAME) *.pyc
	rm -rf __pycache__

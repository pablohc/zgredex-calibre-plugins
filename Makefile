.PHONY: install list remove

PLUGIN_DIR = crosspoint_reader
PLUGIN_NAME = CrossPoint Reader
CALIBRE = /Applications/calibre.app/Contents/MacOS/calibre-customize

install:
	$(CALIBRE) -b $(PLUGIN_DIR)

list:
	$(CALIBRE) -l

remove:
	$(CALIBRE) -r "$(PLUGIN_NAME)"

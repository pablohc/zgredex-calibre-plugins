.PHONY: install list remove zip release bump-patch bump-minor bump-major

PLUGIN_DIR = crosspoint_reader
PLUGIN_NAME = CrossPoint Reader
CALIBRE = /Applications/calibre.app/Contents/MacOS/calibre-customize
VERSION = $(shell python3 -c "import re; m=re.search(r'version\s*=\s*\((\d+),\s*(\d+),\s*(\d+)\)', open('$(PLUGIN_DIR)/driver.py').read()); print(f'{m.group(1)}.{m.group(2)}.{m.group(3)}')")
ZIP_NAME = $(PLUGIN_DIR)-v$(VERSION).zip

install:
	$(CALIBRE) -b $(PLUGIN_DIR)

list:
	$(CALIBRE) -l

remove:
	$(CALIBRE) -r "$(PLUGIN_NAME)"

zip:
	@echo "Packaging $(PLUGIN_DIR) v$(VERSION)..."
	rm -f $(ZIP_NAME)
	cd $(PLUGIN_DIR) && zip -r ../$(ZIP_NAME) . -x '*.pyc' '__pycache__/*' '.DS_Store'
	@echo "Created $(ZIP_NAME)"

BUMP = python3 -c "import re, sys; part = sys.argv[1]; f = '$(PLUGIN_DIR)/driver.py'; txt = open(f).read(); m = re.search(r'version\s*=\s*\((\d+),\s*(\d+),\s*(\d+)\)', txt); M, m_, p = int(m.group(1)), int(m.group(2)), int(m.group(3)); new = {'major': (M+1,0,0), 'minor': (M,m_+1,0), 'patch': (M,m_,p+1)}[part]; open(f,'w').write(txt.replace(m.group(0), f'version = ({new[0]}, {new[1]}, {new[2]})')); print(f'{M}.{m_}.{p} -> {new[0]}.{new[1]}.{new[2]}')"

bump-patch:
	@$(BUMP) patch

bump-minor:
	@$(BUMP) minor

bump-major:
	@$(BUMP) major

release: zip
	@echo "Creating GitHub release v$(VERSION)..."
	gh release create "v$(VERSION)" $(ZIP_NAME) \
		--title "$(PLUGIN_NAME) v$(VERSION)" \
		--generate-notes
	@echo "Released $(PLUGIN_NAME) v$(VERSION)"

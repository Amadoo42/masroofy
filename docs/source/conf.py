import os
import sys
import django

# 1. Setup Django integration
# This points to the project root (where manage.py lives)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../masroofy')))
os.environ['DJANGO_SETTINGS_MODULE'] = 'core.settings'
django.setup()

# 2. Project information
project = 'Masroofy'
copyright = '2026, Ahmad Amin, Seif Lashin, Jana Ali, Yara Hegab'
author = 'Ahmad Amin, Seif Lashin, Jana Ali, Yara Hegab'
release = '1.0'

# 3. General configuration
extensions = [
    'sphinx.ext.autodoc',      # Core library for generating docs from docstrings
    'sphinx.ext.napoleon',    # Supports Google/NumPy style docstrings
    'sphinx.ext.viewcode',    # Adds "source" links next to your code
    'myst_parser',            # Required to read .md files (conventions, etc.)
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# Support both .rst and .md files
source_suffix = {
    '.rst': 'restructuredtext',
    '.md': 'markdown',
}

# 4. Options for HTML output
html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']
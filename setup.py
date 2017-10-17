from setuptools import setup, find_packages

# You can have one or more plugins.  Just list them all here.
# For each one, add a setup function in plugins/__init__.py
#
entry_points = """
[ginga.rv.plugins]
pds4browser_global=plugins:setup_pds4browser_global
pds4browser_local=plugins:setup_pds4browser_local
"""

setup(
    name = 'GingaPDS4Browser',
    version = "0.1.dev",
    description = "PDS4 file browser for the Ginga reference viewer",
    author = "Michael S. P. Kelley",
    license = "BSD",
    # change this to your URL
    install_requires = ["ginga>=2.6.1"],
    packages = find_packages(),
    include_package_data = True,
    package_data = {},
    entry_points = entry_points,
)

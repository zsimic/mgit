from setuptools import setup


setup(
    name="mgit",
    setup_requires="setupmeta",
    versioning="dev",
    author="Zoran Simic zoran@simicweb.com",
    keywords='multiple, git, repos',
    url="https://github.com/zsimic/mgit",
    entry_points={
        "console_scripts": [
            "mgit = mgit.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: POSIX",
        "Operating System :: Unix",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: Implementation :: CPython",
        "Topic :: Software Development :: Build Tools",
        "Topic :: Utilities"
    ],
)

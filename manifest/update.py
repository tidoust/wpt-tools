#!/usr/bin/env python
import argparse
import imp
import os
import sys

import manifest
from . import vcs
from .log import get_logger

here = os.path.dirname(__file__)
localpaths = imp.load_source("localpaths", os.path.abspath(os.path.join(here, os.pardir, "localpaths.py")))


def profile(f):
    import cProfile
    p = cProfile.Profile()
    def inner(*args, **kwargs):
        p.enable()
        try:
            return f(*args, **kwargs)
        finally:
            p.disable()
            p.dump_stats("profile.out")
    return inner


def update(tests_root, manifest, working_copy=False):
    logger = get_logger()
    tree = None
    if not working_copy:
        tree = vcs.Git.for_path(tests_root)
    if tree is None:
        tree = vcs.NoVCS(tests_root)

    return manifest.update(tree)


def update_from_cli(**kwargs):
    tests_root = kwargs["tests_root"]
    path = kwargs["path"]
    assert tests_root is not None

    m = None
    logger = get_logger()

    if not kwargs.get("rebuild", False):
        try:
            m = manifest.load(tests_root, path)
        except manifest.ManifestVersionMismatch:
            logger.info("Manifest version changed, rebuilding")
            m = None
        else:
            logger.info("Updating manifest")

    if m is None:
        m = manifest.Manifest(kwargs["url_base"])

    changed = update(tests_root,
                     m,
                     working_copy=kwargs["work"])
    if changed:
        manifest.write(m, path)


def abs_path(path):
    return os.path.abspath(os.path.expanduser(path))


def create_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-p", "--path", type=abs_path, help="Path to manifest file.")
    parser.add_argument(
        "--tests-root", type=abs_path, help="Path to root of tests.")
    parser.add_argument(
        "-r", "--rebuild", action="store_true", default=False,
        help="Force a full rebuild of the manifest.")
    parser.add_argument(
        "--work", action="store_true", default=False,
        help="Build from the working tree rather than the latest commit")
    parser.add_argument(
        "--url-base", action="store", default="/",
        help="Base url to use as the mount point for tests in this manifest.")
    return parser


def find_top_repo():
    path = here
    rv = None
    while path != "/":
        if vcs.is_git_repo(path):
            rv = path
        path = os.path.abspath(os.path.join(path, os.pardir))

    return rv

@profile
def main(default_tests_root=None):
    opts = create_parser().parse_args()

    if opts.tests_root is None:
        tests_root = None
        if default_tests_root is not None:
            tests_root = default_tests_root
        else:
            tests_root = find_top_repo()

        if tests_root is None:
            print >> sys.stderr, """No git repo found; could not determine test root.
Run again with --test-root"""
            sys.exit(1)

        opts.tests_root = tests_root

    if opts.path is None:
        opts.path = os.path.join(opts.tests_root, "MANIFEST.json")

    update_from_cli(**vars(opts))

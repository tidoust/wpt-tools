import json
import os
import re
from collections import defaultdict
from six import iteritems

from .item import ManualTest, WebdriverSpecTest, Stub, RefTestNode, RefTest, TestharnessTest, SupportFile, ConformanceCheckerTest
from .log import get_logger
from .sourcefile import SourceFile
from .utils import from_os_path, to_os_path, rel_path_to_url


CURRENT_VERSION = 4


class ManifestError(Exception):
    pass


class ManifestVersionMismatch(ManifestError):
    pass


def sourcefile_items(args):
    tests_root, url_base, rel_path, status = args
    source_file = SourceFile(tests_root,
                             rel_path,
                             url_base)
    return rel_path, source_file.manifest_items()


class Manifest(object):
    def __init__(self, url_base="/"):
        assert url_base is not None
        self._path_hash = {}
        self._data = defaultdict(dict)
        self._reftest_nodes_by_url = None
        self.url_base = url_base

    def itertypes(self, *types):
        for item_type in types:
            for path, tests in sorted(iteritems(self._data[item_type])):
                yield item_type, tests

    @property
    def reftest_nodes_by_url(self):
        if self._reftest_nodes_by_url is None:
            by_url = {}
            for path, nodes in iteritems(self._data.get("reftests", {})):
                for node in nodes:
                    by_url[node.url] = node
            self._reftest_nodes_by_url = by_url
        return self._reftest_nodes_by_url

    def get_reference(self, url):
        return self.reftest_nodes_by_url.get(url)

    def update(self, tree):
        tests_root = tree.root
        new_data = defaultdict(dict)
        new_hashes = {}

        reftest_nodes = []

        changed = False
        reftest_changes = False
        local_changes = tree.local_changes()

        for rel_path in tree.list_tree(tests_root):
            content = None
            if rel_path in local_changes:
                content = tree.show_file(rel_path)

            source_file = SourceFile(tests_root,
                                     rel_path,
                                     self.url_base)
            file_hash = source_file.hash

            is_new = rel_path not in self._path_hash
            hash_changed = False

            if not is_new:
                old_hash, old_type = self._path_hash[rel_path]
                if old_hash != file_hash:
                    new_type, manifest_items = source_file.manifest_items()
                    hash_changed = True
                else:
                    new_type, manifest_items = old_type, self._data[old_type][rel_path]
            else:
                new_type, manifest_items = source_file.manifest_items()

            if new_type:
                new_data[new_type][rel_path] = manifest_items
            new_hashes[rel_path] = (file_hash, new_type)

            if is_new or hash_changed:
                changed = True

            if new_type == "reftest":
                reftest_nodes.extend(manifest_items)
                if is_new or hash_changed:
                    reftest_changes = True

        if reftest_changes:
            self._compute_reftests(reftest_nodes)

        self._data = new_data
        self._path_hash = new_hashes

        return changed

    def _compute_reftests(self, reftest_nodes):
        self._reftest_nodes_by_url = {}
        has_inbound = set()
        for item in reftest_nodes:
            for ref_url, ref_type in item.references:
                has_inbound.add(ref_url)

        for item in reftest_nodes:
            # This is proabably not great for pypy...
            if item.url in has_inbound:
                self._reftest_nodes_by_url[item.url] = item
                if item.__class__ == RefTest:
                    item.__class__ = RefTestNode
            elif item.url not in has_inbound and item.__class__ == RefTestNode:
                item.__class__ = RefTest

    def to_json(self):
        out_items = {
            test_type: {
                to_os_path(path):
                [t for t in sorted(test.to_json() for test in tests)]
                for path, tests in iteritems(type_paths)
            }
            for test_type, type_paths in iteritems(self._data)
        }
        rv = {"url_base": self.url_base,
              "paths": self._path_hash,
              "items": out_items,
              "version": CURRENT_VERSION}
        return rv

    @classmethod
    def from_json(cls, tests_root, obj):
        version = obj.get("version")
        if version != CURRENT_VERSION:
            raise ManifestVersionMismatch

        self = cls(url_base=obj.get("url_base", "/"))
        if not hasattr(obj, "items") and hasattr(obj, "paths"):
            raise ManifestError

        self._path_hash = obj["paths"]

        item_classes = {"testharness": TestharnessTest,
                        "reftest": RefTest,
                        "reftest_node": RefTestNode,
                        "manual": ManualTest,
                        "stub": Stub,
                        "wdspec": WebdriverSpecTest,
                        "conformance": ConformanceCheckerTest,
                        "support": SupportFile}

        source_files = {}

        for test_type, type_paths in iteritems(obj["items"]):
            if test_type not in item_classes:
                raise ManifestError
            test_cls = item_classes[test_type]
            tests = defaultdict(list)
            for path, manifest_tests in iteritems(type_paths):
                for test in manifest_tests:
                    manifest_item = test_cls.from_json(self,
                                                       tests_root,
                                                       path,
                                                       test,
                                                       source_files=source_files)
                    tests[path].append(manifest_item)
            self._data[test_type] = tests

        return self


def load(tests_root, manifest):
    logger = get_logger()

    # "manifest" is a path or file-like object.
    if isinstance(manifest, basestring):
        if os.path.exists(manifest):
            logger.debug("Opening manifest at %s" % manifest)
        else:
            logger.debug("Creating new manifest at %s" % manifest)
        try:
            with open(manifest) as f:
                rv = Manifest.from_json(tests_root, json.load(f))
        except IOError:
            return None
        return rv

    return Manifest.from_json(tests_root, json.load(manifest))


def write(manifest, manifest_path):
    with open(manifest_path, "wb") as f:
        json.dump(manifest.to_json(), f, sort_keys=True, indent=1, separators=(',', ': '))
        f.write("\n")

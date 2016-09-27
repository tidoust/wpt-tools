import os
import subprocess


class Git(object):
    def __init__(self, repo_root):
        self.root = os.path.abspath(repo_root)
        self.git = Git.get_func(repo_root)

    @staticmethod
    def get_func(repo_path):
        def git(cmd, *args):
            full_cmd = ["git", cmd] + list(args)
            return subprocess.check_output(full_cmd, cwd=repo_path, stderr=subprocess.STDOUT)
        return git

    @classmethod
    def for_path(cls, path=None):
        if path is None:
            path = os.path.dirname(__file__)
        git = Git.get_func(path)
        try:
            return cls(git("rev-parse", "--show-toplevel").rstrip())
        except subprocess.CalledProcessError:
            return None

    def local_changes(self, path=None):
        changes = {}
        cmd = ["status", "-z", "--ignore-submodules=all"]
        if path is not None:
            path = os.path.relpath(os.path.abspath(path), self.root)
            cmd.extend(["--", path])
        data = self.git(*cmd)

        if data == "":
            return changes

        rename_data = None
        for entry in data.split("\0")[:-1]:
            if rename_data is not None:
                status, rel_path = entry.split(" ")
                if status[0] == "R":
                    rename_data = (rel_path, status)
                else:
                    changes[rel_path] = (status, None)
            else:
                rel_path = entry
                changes[rel_path] = rename_data
                rename_data = None
        return changes

    def list_tree(self, path=None):
        cmd = ["ls-tree", "-r", "-z", "--name-only", "HEAD"]
        if path is not None:
            path = os.path.relpath(os.path.abspath(path), self.root)
            cmd.extend(["--", path])
        for rel_path in self.git(*cmd).split("\0")[:-1]:
            if not os.path.isdir(os.path.join(self.root, rel_path)):
                yield rel_path

    def show_file(self, path):
        path = os.path.relpath(os.path.abspath(path), self.root)
        return self.git("show", "HEAD:%s" % path)


class NoVCS(object):
    def __init__(self, root):
        self.root = root
        from gitignore import gitignore
        self.path_filter = gitignore.PathFilter(self.root)

    def local_changes(self):
        return {}

    def list_tree(self, path=None):
        if path is not None:
            path = os.path.relpath(os.path.abspath(path), self.root)
        else:
            path = self.root

        is_root = True
        for dir_path, dir_names, filenames in os.walk(path):
            rel_root = os.path.relpath(dir_path, self.root)

            if is_root:
                dir_names[:] = [item for item in dir_names if item not in
                                ["tools", "resources", ".git"]]
                is_root = False

            for filename in filenames:
                rel_path = os.path.join(rel_root, filename)
                if self.path_filter(rel_path):
                    yield rel_path

    def show_file(self, path):
        with open(path, "rb") as f:
            return f.read()

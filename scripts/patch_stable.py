#!/usr/bin/python3

import pygit2
import re
import sys
import argparse
from os.path import expanduser
parser = argparse.ArgumentParser(description='Patch stable branch.')
parser.add_argument('-i', '--interactive', action="store_true", help="interactive: pause to resolve conflicts")
parser.add_argument('repo', help='repository to patch')
parser.add_argument('target_branch', help='branch to patch')
parser.add_argument('stable_branch', help="pick patches cc'd to this stable branch")
args = parser.parse_args(sys.argv[1:])

mesa = pygit2.Repository(expanduser(args.repo))

master = mesa.lookup_reference('refs/heads/master').target
target_branch_ref = 'refs/heads/' + args.target_branch
mesa.checkout(target_branch_ref)
target_branch = mesa.lookup_reference(target_branch_ref).target

branch_point = mesa.merge_base(master, target_branch)

master_commits = []
fixes = {}
for commit in mesa.walk(master):
    if commit.id == branch_point:
        break
    for aline in commit.message.splitlines():
        aline = aline.lower()
        if ("fixes:" in aline):
            try:
                broken_commit = aline.split()[1]
                m = re.match("[0-9a-fA-F]+", broken_commit)
                broken = mesa.get(m.group(0)).id
                broken_branch_point = mesa.merge_base(target_branch, broken)
                if broken_branch_point == broken:
                    # broken commit is in the stable branch
                    fixes[commit.id] = broken
                else:
                    # fixes a commit after the branch point
                    continue
            except:
                # "fixes:" lined did not contain a valid sha
                pass
            master_commits.append(commit.id)
            break
        if ("cc:" in aline):
            if ("mesa-stable" in aline):
                master_commits.append(commit.id)
                break
            if (args.stable_branch in aline):
                master_commits.append(commit.id)
                break

master_commits.reverse()

stable_commits = {}
for commit in mesa.walk(target_branch):
    if commit.id == branch_point:
        break
    for aline in commit.message.splitlines():
        aline = aline.lower()
        if "cherry-ignore:" in aline or "cherry-applies:" in aline:
            try:
                ignore_commit = aline.split()[1]
                m = re.match("[0-9a-fA-F]+", ignore_commit)
                ignore = mesa.get(m.group(0)).id
                broken_branch_point = mesa.merge_base(target_branch, broken)
                stable_commits[ignore] = commit.id
            except:
                # "cherry-" line did not contain a valid sha
                pass

cherry_ignores = []
for patch in master_commits:
    if patch in stable_commits:
        continue
    # TODO: check if fixes in the history of the branch
    head = mesa.lookup_reference('refs/heads/18.0').target
    cherry = mesa.cherrypick(patch)
    src_commit = mesa.get(patch)
    while mesa.index.conflicts:
        print("Failed to cherry-pick: " + str(patch))
        print("Ignore? [y/n]: ", end="", flush=True)
        response = sys.stdin.readline()
        mesa.index.read()
        if response[0] == 'y':
            mesa.state_cleanup()
            mesa.reset(head, pygit2.GIT_RESET_HARD)
            cherry_ignores.append(str(patch) + " " + src_commit.message.splitlines()[0])
            continue

    # else no conflicts
    mesa.index.write()
    mesa.create_commit("refs/heads/18.0", src_commit.author, src_commit.author,
                       str(src_commit.message) + "\ncherry-applies: " + str(patch),
                       mesa.index.write_tree(), [head])
    mesa.state_cleanup()

if not cherry_ignores:
    sys.exit(0)

commit_message = "Automated patching of stable branch\n"
for ignore in cherry_ignores:
    commit_message += "\ncherry-ignore: " + ignore
author = pygit2.Signature('Mark Janes', 'mark.a.janes@intel.com')
tree = mesa.index.write_tree()
head = mesa.lookup_reference('refs/heads/18.0').target
mesa.create_commit("refs/heads/18.0", author, author,
                   commit_message,
                   tree, [head])

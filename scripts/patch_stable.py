#!/usr/bin/python3

import argparse
import git
import os.path
import re
import smtplib
import sys

parser = argparse.ArgumentParser(description='Patch stable branch.')
parser.add_argument('-i', '--interactive', action="store_true", help="interactive: pause to resolve conflicts")
parser.add_argument('repo', help='repository to patch')
parser.add_argument('target_branch', help='branch to patch')
parser.add_argument('stable_branch', help="pick patches cc'd to this stable branch")
args = parser.parse_args(sys.argv[1:])

mesa_dir = os.path.expanduser(args.repo)
mesa = git.Repo(mesa_dir)

master = mesa.heads.master
#target_branch_ref = 'refs/heads/' + args.target_branch
mesa.git.checkout(args.target_branch)

branch_point = mesa.merge_base(master, args.target_branch)[0]

stable_commits = {}
for aline in open(mesa_dir + "/bin/.cherry-ignore").readlines():
    words = aline.split()
    if not words:
        continue
    if words[0].startswith('#'):
        continue
    stable_commits[aline.split()[0]] = "cherry-ignore"

for commit in mesa.iter_commits(args.target_branch):
    if commit == branch_point:
        break
    for aline in commit.message.splitlines():
        aline = aline.lower()
        if "cherry picked from commit" in aline:
            words = aline.split()
            applied = words[-1][:-1]
            stable_commits[applied] = commit.hexsha
        if "cherry-ignore:" in aline or "cherry-applies:" in aline:
            try:
                ignore_commit = aline.split()[1]
                m = re.match("[0-9a-fA-F]+", ignore_commit)
                ignore = mesa.commit(m.group(0)).hexsha
                stable_commits[ignore] = commit.hexsha
            except:
                # "cherry-" line did not contain a valid sha
                pass

master_commits = []
fixes = {}
for commit in mesa.iter_commits("master"):
    if commit == branch_point:
        break
    fixes_found = False
    for aline in commit.message.splitlines():
        aline = aline.lower()
        if ("fixes:" in aline):
            try:
                broken_commit = aline.split()[1]
                m = re.match("[0-9a-fA-F]+", broken_commit)
                broken = mesa.commit(m.group(0))
                fixes_found = True
                broken_branch_point = mesa.merge_base(args.target_branch, broken)[0]
                if broken_branch_point == broken:
                    # broken commit is in the stable branch
                    fixes[commit.hexsha] = broken.hexsha
                else:
                    # fixes a commit after the branch point
                    continue
            except:
                # "fixes:" lined did not contain a valid sha
                continue
            if commit.hexsha not in stable_commits:
                master_commits.append(commit.hexsha)
            break
    if fixes_found:
        #Many patches have both CC and fixes, and you don't
        # want to select based on the CC.
        continue

    # else, there may be a CC: that would cause the patch to get
    # backported.  
    for aline in commit.message.splitlines():
        aline = aline.lower()
        if ("cc:" in aline):
            branches = aline.split()[1:]
            if ("mesa-stable" in branches[0]) and commit.hexsha not in stable_commits:
                # commit CC's stable without a specific branch
                # CC: <mesa-stable@lists.freedesktop.org>
                master_commits.append(commit.hexsha)
                break
            for branch in branches:
                if (args.stable_branch in branch) and commit.hexsha not in stable_commits:
                    # commit CC's the specific branch
                    # CC: "17.3 18.0" <mesa-stable@lists.freedesktop.org>
                    master_commits.append(commit.hexsha)
                    break

master_commits.reverse()


cherry_ignores = []
for src_commit in master_commits:
    if src_commit in stable_commits:
        continue
    # TODO: check if fixes in the history of the branch
    # head = mesa.lookup_reference('refs/heads/18.0').target
    print("Cherry-picking " + src_commit)
    try:
        cherry = mesa.git.cherry_pick(["-x", src_commit])
    except(git.GitCommandError):
        commit_obj = mesa.commit(src_commit)
        if not args.interactive:
            print("\tFailed to cherry-pick: " + str(src_commit))
            mesa.git.cherry_pick(["--abort"])
            cherry_ignores.append(src_commit + " " + commit_obj.message.splitlines()[0])
            continue
        while mesa.index.unmerged_blobs():
            print("\tFailed to cherry-pick: " + str(src_commit))
            print("\tIgnore? [y/n]: ", end="", flush=True)
            response = sys.stdin.readline()
            if response[0] == 'y':
                mesa.git.cherry_pick(["--abort"])
                cherry_ignores.append(src_commit + " " + commit_obj.message.splitlines()[0])
                break
            elif not mesa.index.unmerged_blobs():
                mesa.index.commit(message = str(commit_obj.message)
                                  + "\n(cherry picked from commit "
                                  + src_commit + ")",
                                  author=commit_obj.author, committer=commit_obj.author)
                mesa.head.reset()
                break

if not cherry_ignores:
    sys.exit(0)

with open(mesa_dir + "/bin/.cherry-ignore", "a") as ci:
    ci.writelines("{ignore}\n".format(ignore=i) for i in cherry_ignores)
mesa.index.add(["bin/.cherry-ignore"])
mesa.index.commit(message = "Automated patching of stable branch")
sys.exit(1)

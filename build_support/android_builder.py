# Copyright (C) Intel Corp.  2018.  All Rights Reserved.

# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:

# The above copyright notice and this permission notice (including the
# next paragraph) shall be included in all copies or substantial
# portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE COPYRIGHT OWNER(S) AND/OR ITS SUPPLIERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

#  **********************************************************************/
#  * Authors:
#  *   Clayton Craft <clayton.a.craft@intel.com>
#  **********************************************************************/
import glob
import os
import subprocess
from . import cpu_count
from . import Options
from . import ProjectMap
from . import run_batch_command
from . import rmtree
from . import git_clean
from . import Export


class AndroidBuilder(object):
    def __init__(self, src_location, module):
        self._options = Options()
        self._project_map = ProjectMap()
        self._env = {}

        self._src_dir = os.path.join(self._project_map._source_root, "repos",
                                     "android")
        # Location of mesa source to build
        mesa_src = os.path.join(self._project_map._source_root, "repos",
                                "mesa")
        if not os.path.exists(mesa_src):
            assert os.path.exists(mesa_src), ("ERROR: Mesa source directory "
                                              "not found: {}".format(mesa_src))
        # Sometimes builds fail if the previous build failed, so remove entire
        # source tree before trying
        if os.path.exists(self._src_dir):
            rmtree(self._src_dir)
        print("Copying android source from: {}".format(src_location))
        run_batch_command(["cp", "-al", os.path.expanduser(src_location),
                           self._src_dir])
        # Local location of mesa source in Android tree
        self._mesa_local_src = os.path.join(self._project_map._source_root,
                                            "repos/android/vendor/intel",
                                            "external/android_ia/mesa")
        # Create symlink from mesa source to subdir in android tree
        if os.path.exists(self._mesa_local_src):
            if os.path.islink(self._mesa_local_src):
                os.remove(self._mesa_local_src)
            else:
                rmtree(self._mesa_local_src)
        os.symlink(mesa_src, self._mesa_local_src)

        self._env['ANDROID_TARGET'] = "androidia_64-eng"
        self._env['ANDROID_SOURCE'] = self._src_dir
        self._env['ANDROID_MODULE'] = module
        self._env['NUM_CPUS'] = str(cpu_count())
        self._build_helper = os.path.join(self._project_map.source_root(),
                                          "repos/mesa_ci/build_support",
                                          "android_builder.sh")

    def build(self):
        # apply patches if they exist
        for patch in sorted(glob.glob(os.path.join(
                            self._project_map.project_build_dir(),
                            "*.patch"))):
            os.chdir(self._mesa_local_src)
            try:
                run_batch_command(["git", "am", patch])
            except subprocess.CalledProcessError:
                print("WARN: failed to apply patch: {}".format(patch))
                run_batch_command(["git", "am", "--abort"])
        try:
            run_batch_command([self._build_helper, 'build'], env=self._env)
        except subprocess.CalledProcessError:
            Export().create_failing_test("Android Build Test",
                                         ("ERROR: Failed to build Mesa. "
                                          "See the console log for the "
                                          "android-buildtest component "
                                          "for more details."))
        # Remove any applied patches so they do not interfere with
        # any future tests that might use this mesa repo
        git_clean(self._mesa_local_src)

    def clean(self):
        git_clean(self._mesa_local_src)
        run_batch_command([self._build_helper, "clean"], env=self._env)

    def test(self):
        pass

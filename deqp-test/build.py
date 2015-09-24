#!/usr/bin/python

import bz2
import os
import re
import sys
import xml.etree.ElementTree  as ET

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), ".."))
import build_support as bs

class DeqpTrie:
    def __init__(self):
        self._trie = {}
        
    def add_txt(self, txt_file):
        fh = None
        if (txt_file[-4:] == ".bz2"):
            fh = bz2.BZ2File(txt_file)
        else:
            fh = open(txt_file)

        for line in fh.readlines():
            line = line.strip()
            self.add_line(line)

    def add_line(self, line):
        self._add_split_line(line.split("."))
            
    def _add_split_line(self, line):
        if not line:
            return
        group = line[0]
        if line == "performance":
            return
        if not self._trie.has_key(group):
            self._trie[group] = DeqpTrie()
        self._trie[group]._add_split_line(line[1:])
            
    def add_xml(self, xml_file):
        current_trie = None
        if "dEQP-GLES2-cases" in xml_file:
            current_trie = DeqpTrie()
            self._trie["dEQP-GLES2"] = current_trie
        elif "dEQP-GLES3-cases" in xml_file:
            current_trie = DeqpTrie()
            self._trie["dEQP-GLES3"] = current_trie
        else:
            return
        root = ET.parse(xml_file).getroot()
        for tag in root:
            current_trie._add_tag(tag)

    def _add_tag(self, tag):
        name = tag.attrib["Name"]
        if name == "performance":
            return
        if not self._trie.has_key(name):
            self._trie[name] = DeqpTrie()

        for child in tag:
            self._trie[name]._add_tag(child)

    def filter(self, blacklist):
        if not blacklist._trie and self._trie:
            # caller is filtering out a group of tests with a common
            # prefix.
            self._trie = {}
        for group in blacklist._trie.keys():
            if group not in self._trie:
                print "ERROR: blacklist of " + group + " not in tests"
                continue
            self._trie[group].filter(blacklist._trie[group])
            if len(self._trie[group]._trie) == 0:
                del(self._trie[group])

    def write_caselist(self, outfh, prefix=""):
        items = self._trie.items()
        # ensure stable order, so sharding will work correctly
        items.sort()
        for group, trie in items:
            if len(trie._trie) == 0:
                outfh.write(prefix + "." + group + "\n")
                continue
            # else
            if prefix:
                group = prefix + "." + group
            trie.write_caselist(outfh, group)
            
class DeqpBuilder:
    def __init__(self):
        o = bs.Options()
        pm = bs.ProjectMap()
        self.build_root = pm.build_root()
        libdir = "x86_64-linux-gnu"
        if o.arch == "m32":
            libdir = "i386-linux-gnu"
        self.env = { "LD_LIBRARY_PATH" : self.build_root + "/lib:" + \
                     self.build_root + "/lib/" + libdir + ":" + self.build_root + "/lib/dri",
                     "LIBGL_DRIVERS_PATH" : self.build_root + "/lib/dri",
                     "GBM_DRIVERS_PATH" : self.build_root + "/lib/dri",
                     # fixes dxt subimage tests that fail due to a
                     # combination of unreasonable tolerances and possibly
                     # bugs in debian's s2tc library.  Recommended by nroberts
                     "S2TC_DITHER_MODE" : "NONE",
                     # forces deqp to run headless
                     "EGL_PLATFORM" : "surfaceless"
        }

    def build(self):
        pass

    def clean(self):
        pass

    def test(self):
        # todo: now that there is more than one component that needs
        # to call mesa_version, it should be moved to a more sharable
        # location
        mesa_version = bs.PiglitTester().mesa_version()
        if "10.5" in mesa_version or "10.6" in mesa_version:
            print "WARNING: deqp not supported on 10.6 and earlier."
            return
        
        o = bs.Options()
        pm = bs.ProjectMap()
        src_dir = pm.project_source_dir(pm.current_project())
        savedir = os.getcwd()

        deqp_options = ["./deqp-gles2",
                        "--deqp-surface-type=fbo",
                        "--deqp-log-images=disable",
                        "--deqp-surface-width=256",
                        "--deqp-surface-height=256"]


        expectations_dir = None
        # identify platform
        if "byt" in o.hardware:
            expectations_dir = src_dir + "/chromiumos-autotest/graphics_dEQP/expectations/baytrail"
        elif "bdw" in o.hardware:
            expectations_dir = src_dir + "/chromiumos-autotest/graphics_dEQP/expectations/broadwell"
        elif "hsw" in o.hardware:
            expectations_dir = src_dir + "/chromiumos-autotest/graphics_dEQP/expectations/haswell"
        elif "ivb" in o.hardware:
            expectations_dir = src_dir + "/chromiumos-autotest/graphics_dEQP/expectations/ivybridge"
        elif "snb" in o.hardware:
            expectations_dir = src_dir + "/chromiumos-autotest/graphics_dEQP/expectations/sandybridge"
        elif "bsw" in o.hardware:
            expectations_dir = pm.project_build_dir(pm.current_project()) + "/bsw_expectations"

        conf_file = bs.get_conf_file(o.hardware, o.arch, "deqp-test")

        for module in ["gles2", "gles3"]:
            skip = DeqpTrie()
            # for each skip list, parse into skip trie
            if expectations_dir and os.path.exists(expectations_dir):
                for askipfile in os.listdir(expectations_dir):
                    if module not in askipfile.lower():
                        continue
                    skip.add_txt(expectations_dir + "/" + askipfile)
            else:
                skip._trie["empty"] = None

            # create test trie
            os.chdir(self.build_root + "/opt/deqp/modules/" + module)
            # generate list of tests
            bs.run_batch_command(["./deqp-" + module] + deqp_options + ["--deqp-runmode=xml-caselist"],
                                 env=self.env)
            outfile = "dEQP-" + module.upper() + "-cases.xml"
            assert(os.path.exists(outfile))
            testlist = DeqpTrie()
            testlist.add_xml(outfile)

            # filter skip trie from testlist trie
            testlist.filter(skip)

            # filter intermittent tests
            # TODO(janesma) : write bug
            skips = ["functional.fragment_ops.interaction.basic_shader",
                     "functional.shaders.random.basic_expression.combined",
                     "functional.shaders.random.conditionals.combined",
                     # fails intermittently on at least bdw and hsw
                     "functional.flush_finish.flush",
                     "functional.flush_finish.finish"
                     ]
            if "snb" in o.hardware:
                skips = skips + ["functional.shaders.random.texture.vertex.45",
                                 "functional.shaders.random.texture.vertex.1"]
                
            intermittent = DeqpTrie()
            for skip in skips:
                intermittent.add_line("dEQP-" + module.upper() + "." + skip)
            testlist.filter(intermittent)

            # generate testlist file
            caselist_fn = module + "-cases.txt"
            caselist = open(caselist_fn, "w")
            testlist.write_caselist(caselist)
            caselist.close()
            self.shard_caselist(caselist_fn, o.shard)

        os.chdir(savedir)

        # invoke piglit
        self.env["PIGLIT_DEQP_GLES2_BIN"] = self.build_root + "/opt/deqp/modules/gles2/deqp-gles2"
        self.env["PIGLIT_DEQP_GLES2_EXTRA_ARGS"] =  ("--deqp-surface-type=fbo "
                                                     "--deqp-log-images=disable "
                                                     '--deqp-surface-width=256 '
                                                     '--deqp-surface-height=256 '
                                                     "--deqp-caselist-file=" +
                                                     self.build_root + "/opt/deqp/modules/gles2/gles2-cases.txt")
        self.env["PIGLIT_DEQP_GLES3_EXE"] = self.build_root + "/opt/deqp/modules/gles3/deqp-gles3"
        self.env["PIGLIT_DEQP_GLES3_EXTRA_ARGS"] = ("--deqp-surface-type=fbo "
                                                    "--deqp-log-images=disable "
                                                    '--deqp-surface-width=256 '
                                                    '--deqp-surface-height=256 '
                                                    "--deqp-caselist-file=" +
                                                    self.build_root + "/opt/deqp/modules/gles3/gles3-cases.txt")
        out_dir = self.build_root + "/test/" + o.hardware

        include_tests = []
        if o.retest_path:
            testlist = bs.TestLister(o.retest_path + "/test/")
            for atest in testlist.Tests():
                test_name_good_chars = re.sub('[_ !:=]', ".", atest.test_name)
                # drop the spec
                test_name = ".".join(test_name_good_chars.split(".")[1:])
                include_tests = include_tests + ["--include-tests", test_name]
            
        cmd = [self.build_root + "/bin/piglit",
               "run",
               "-p", "gbm",
               "-b", "junit",
               "--config", conf_file,
               "-c",
               "--junit_suffix", "." + o.hardware + o.arch] + \
            include_tests + \
            ["deqp_gles2", "deqp_gles3", out_dir ]
        
        bs.run_batch_command(cmd, env=self.env,
                             expected_return_code=None,
                             streamedOutput=True)

        single_out_dir = self.build_root + "/../test"
        if not os.path.exists(single_out_dir):
            os.makedirs(single_out_dir)

        if os.path.exists(out_dir + "/results.xml"):
            # Uniquely name all test files in one directory, for
            # jenkins
            filename_components = ["/piglit-deqp",
                                   o.hardware,
                                   o.arch]
            if o.shard != "0":
                # only put the shard suffix on for non-zero shards.
                # Having _0 suffix interferes with bisection.
                filename_components.append(o.shard)

            revisions = bs.RepoSet().branch_missing_revisions()
            print "INFO: filtering tests from " + out_dir + "/results.xml"
            self.filter_tests(revisions,
                              out_dir + "/results.xml",
                              single_out_dir + "_".join(filename_components) + ".xml")

            # create a copy of the test xml in the source root, where
            # jenkins can access it.
            cmd = ["cp", "-a", "-n",
                   self.build_root + "/../test", pm.source_root()]
            bs.run_batch_command(cmd)
            bs.Export().export_tests()
        else:
            print "ERROR: no results at " + out_dir + "/results.xml"

        bs.PiglitTester().check_gpu_hang()

    def shard_caselist(self, caselist_fn, shard):
        if shard == "0":
            return

        assert(":" in shard)
        shardargs = shard.split(":")
        shardno = int(shardargs[0])
        shardcount = int(shardargs[1])
        assert(shardno <= shardcount)

        shard_tests = []
        test_no = 0
        test_list = open(caselist_fn).readlines()
        for a_test in test_list:
            if (test_no % shardcount) + 1 == shardno:
                shard_tests.append(a_test)
            test_no = test_no + 1

        bs.rmtree(caselist_fn)
        caselist_fh = open(caselist_fn, "w")
        for a_test in shard_tests:
            caselist_fh.write(a_test)

    def filter_tests(self, revisions, infile, outfile):
        """this method is ripped bleeding from builders.py / PiglitTester"""
        t = ET.parse(infile)
        for a_suite in t.findall("testsuite"):
            # remove skipped tests, which uses ram on jenkins when
            # displaying and provides no value.  
            for a_skip in a_suite.findall("testcase/skipped/.."):
                if a_skip.attrib["status"] in ["crash", "fail"]:
                    continue
                a_suite.remove(a_skip)

            # for each failure, see if there is an entry in the config
            # file with a revision that was missed by a branch
            for afail in a_suite.findall("testcase/failure/..") + a_suite.findall("testcase/error/.."):
                piglit_test = bs.PiglitTest("foo", "foo", afail)
                regression_revision = piglit_test.GetConfRevision()
                abbreviated_revisions = [a_rev[:6] for a_rev in revisions]
                for abbrev_rev in abbreviated_revisions:
                    if abbrev_rev in regression_revision:
                        print "stripping: " + piglit_test.test_name + " " + regression_revision
                        a_suite.remove(afail)
                        # a test may match more than one revision
                        # encoded in a comment
                        break
                
        t.write(outfile)

class SlowTimeout:
    def __init__(self):
        self.hardware = bs.Options().hardware

    def GetDuration(self):
        return 500

bs.build(DeqpBuilder(), time_limit=SlowTimeout())
        

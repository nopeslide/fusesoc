import multiprocessing
import os
import logging

from fusesoc import utils
from .simulator import Simulator

logger = logging.getLogger(__name__)

CONFIG_MK_TEMPLATE = """#Auto generated by FuseSoC

TOP_MODULE        := {top_module}
VC_FILE           := {vc_file}
VERILATOR_OPTIONS := {verilator_options}
"""

MAKEFILE_TEMPLATE = """#Auto generated by FuseSoC

include config.mk

#Assume a local installation if VERILATOR_ROOT is set
ifeq ($(VERILATOR_ROOT),)
VERILATOR ?= verilator
else
VERILATOR ?= $(VERILATOR_ROOT)/bin/verilator
endif

V$(TOP_MODULE): V$(TOP_MODULE).mk
	$(MAKE) -f $<

V$(TOP_MODULE).mk:
	$(VERILATOR) -f $(VC_FILE) $(VERILATOR_OPTIONS)
"""

class Verilator(Simulator):

    def configure(self, args):
        if self.system.verilator is None:
            raise RuntimeError("verilator section is missing in top-level core file")

        self.top_module = self.system.verilator.top_module

        if self.top_module == '':
            raise RuntimeError("'" + system.name.name + "' miss a mandatory parameter 'top_module'")

        skip = not (self.system.verilator.cli_parser == 'fusesoc')
        super(Verilator, self).configure(args, skip_params = skip)
        self._write_config_files()

    def _write_config_files(self):
        #Future improvement: Separate include directories of c and verilog files
        incdirs = set()
        src_files = []

        (src_files, incdirs) = self._get_fileset_files()

        self.verilator_file = self.system.sanitized_name + '.vc'

        with open(os.path.join(self.work_root,self.verilator_file),'w') as f:
            f.write('--Mdir .\n')
            if self.system.verilator.source_type == 'systemC':
                f.write('--sc\n')
            else:
                f.write('--cc\n')

            for core in self.cores:
                if core.verilator:
                    for lib in core.verilator.libs:
                        f.write('-LDFLAGS {}\n'.format(lib))
            for include_dir in incdirs:
                f.write("+incdir+" + include_dir + '\n')
                f.write("-CFLAGS -I{}\n".format(include_dir))
            opt_c_files = []
            for src_file in src_files:
                if src_file.file_type.startswith("systemVerilogSource") or src_file.file_type.startswith("verilogSource"):
                    f.write(src_file.name + '\n')
                elif src_file.file_type in ['cppSource', 'systemCSource', 'cSource']:
                    opt_c_files.append(src_file.name)
            f.write('--top-module {}\n'.format(self.top_module))
            f.write('--exe\n')
            f.write('\n'.join(opt_c_files))
            f.write('\n')
            f.write(''.join(['-G{}={}\n'.format(key, self._param_value_str(value)) for key, value in self.vlogparam.items()]))
            f.write(''.join(['-D{}={}\n'.format(key, self._param_value_str(value)) for key, value in self.vlogdefine.items()]))

        with open(os.path.join(self.work_root, 'Makefile'), 'w') as makefile:
            makefile.write(MAKEFILE_TEMPLATE)

        with open(os.path.join(self.work_root, 'config.mk'), 'w') as config_mk:
            config_mk.write(CONFIG_MK_TEMPLATE.format(
                top_module        = self.top_module,
                vc_file           = self.verilator_file,
                verilator_options = ' '.join(self.system.verilator.verilator_options)))

    def build(self):
        super(Verilator, self).build()

        logger.info("Building simulation model")

        if not os.getenv('VERILATOR_ROOT') and not utils.which('verilator'):
            raise RuntimeError("VERILATOR_ROOT not set and there is no verilator program in your PATH")

        # Do parallel builds with <number of cpus> * 2 jobs.
        make_job_count = multiprocessing.cpu_count() * 2

        _s = os.path.join(self.work_root, 'verilator.{}.log')
        l = utils.Launcher('make',
                           ['-j', str(make_job_count)],
                           cwd=self.work_root,
                           stderr = open(_s.format('err'),'w'),
                           stdout = open(_s.format('out'),'w')).run()

    def run(self, args):
        fusesoc_cli_parser = (self.system.verilator.cli_parser == 'fusesoc')

        super(Verilator, self).run(args)

        if fusesoc_cli_parser:
            _args = []
            for key, value in self.plusarg.items():
                _args += ['+{}={}'.format(key, self._param_value_str(value))]
            for key, value in self.cmdlinearg.items():
                _args += ['--{}={}'.format(key, self._param_value_str(value))]
        else:
            _args = args
        logger.info("Running simulation")
        utils.Launcher('./V' + self.system.verilator.top_module,
                       _args,
                       cwd=self.work_root,
                       env = self.env).run()

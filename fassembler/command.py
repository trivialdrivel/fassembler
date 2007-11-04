import sys
import re
from cmdutils import OptionParser, CommandError, main_func
import pkg_resources
from fassembler.filemaker import Maker
from fassembler.config import ConfigParser
from fassembler.text import indent

## The long description of how this command works:
description = """\
fassembler assembles files.

All files will be installed under BASE_DIR, typically in a
subdirectory for the project.

To get a list of PROJECTs you can install, use %prog --list-projects

To set a configuration variable, use VARIABLE=VALUE, or
[SECTION]VARIABLE=VALUE.  If you do not use [SECTION] then the
variable will be set globally.
"""

parser = OptionParser(
    usage="%prog [OPTIONS] BASE_DIR PROJECT [PROJECT...] VARIABLES",
    version_package='fassembler',
    description=description,
    use_logging=True,
    )

parser.add_option(
    '-c', '--config',
    metavar='CONFIG_FILE',
    dest='configs',
    action='append',
    default=[],
    help='Config file to load with overrides (you may use this more than once)')

parser.add_option(
    '-n', '--simulate',
    action='store_true',
    dest='simulate',
    help='Simulate (do not write any files or make changes)')

parser.add_option(
    '-i', '--interactive',
    action='store_true',
    dest='interactive',
    help='Ask questions interactively')

parser.add_option(
    '-H', '--project-help',
    action='store_true',
    dest='project_help',
    help='Show information about what the project builders do')

parser.add_option(
    '--list-projects',
    action='store_true',
    dest='list_projects',
    help="List available projects")

parser.add_verbose()

@main_func(parser)
def main(options, args):
    if options.list_projects:
        if args:
            raise CommandError(
                "You cannot use arguments with --list-projects")
        list_projects(options)
        return
    if len(args) < 2:
        raise CommandError(
            "You must provide at least a base directory and one project")
    base_dir = args[0]
    project_names, variables = parse_positional(args[1:])
    logger = options.logger
    config = load_configs(options.configs)
    for section, name, value in variables:
        section = section or 'DEFAULT'
        if not config.has_section(section):
            config.add_section(section)
        config.set(section, name, value, filename='<cmdline>')
    maker = Maker(base_dir, simulate=options.simulate,
                  interactive=options.interactive, logger=logger)
    projects = []
    for project_name in project_names:
        logger.debug('Finding package %s' % project_name)
        ProjectClass = find_project_class(project_name, logger)
        if ProjectClass is None:
            raise BadCommand('Could not find project %s' % project_name)
        project = ProjectClass(project_name, maker, logger, config)
        projects.append(project)
    for project in projects:
        try:
            project.confirm_settings()
        except Exception, e:
            logger.fatal('Error in project %s' % project.project_name)
            logger.fatal('  Error: %s' % e)
            continue
        if options.project_help:
            description = project.make_description()
            print description
        else:
            if len(projects) > 1:
                logger.notify('Starting project %s' % project.project_name)
                logger.indent += 2
            try:
                project.run()
                logger.notify('Done with project %s' % project_name)
            finally:
                if len(projects) > 1:
                    logger.indent -= 2
    if not options.project_help:
        logger.notify('Installation successful.')

_var_re = re.compile(r'^(?:\[(\w+)\])?\s*(\w+)=(.*)$')

def parse_positional(args):
    project_names = []
    variables = []
    for arg in args:
        match = _var_re.search(arg)
        if match:
            variables.append((match.group(1), match.group(2), match.group(3)))
        else:
            project_names.append(arg)
    return project_names, variables

def find_project_class(project_name, logger):
    if ':' in project_name:
        project_name, ep_name = project_name.split(':', 1)
    else:
        ep_name = 'main'
    try:
        dist = pkg_resources.get_distribution(project_name)
    except pkg_resources.DistributionNotFound, e:
        if ep_name != 'main':
            ## FIXME: log something?
            return None
        logger.debug('Could not get distribution %s: %s' % (project_name, e))
        options = pkg_resources.iter_entry_points('fassembler.project', project_name)
        if not options:
            logger.fatal('NO entry points in [fassembler.project] found with name %s' % project_name)
            return None
        if len(options) > 1:
            logger.fatal('More than one entry point in [fassembler.project] found with name %s: %s'
                         % (project_name, ', '.join(map(repr, options))))
            return None
        return options[0].load()
    else:
        ep = dist.get_entry_info('fassembler.project', ep_name)
        logger.debug('Found entry point %s:main = %s' % (dist, ep))
        return ep.load()

def load_configs(configs):
    conf = ConfigParser()
    ## FIXME: test that all configs exist
    conf.read(configs)
    return conf

############################################################
## Project listing
############################################################

def list_projects(options):
    import traceback
    from cStringIO import StringIO
    for ep in pkg_resources.iter_entry_points('fassembler.project'):
        print '%s (from %s:%s)' % (ep_name(ep), ep.module_name, '.'.join(ep.attrs))
        try:
            obj = ep.load()
        except:
            out = StringIO()
            out.write('Exception loading entry point:\n')
            traceback.print_exc(file=out)
            desc = out.getvalue()
        else:
            desc = obj.__doc__
        desc = indent(desc, '  ') or '(undocumented)'
        print desc
        print

def ep_name(ep):
    if ep.name == 'main':
        return str(ep.dist.project_name)
    else:
        return '%s:%s' % (ep.dist.project_name, ep.name)

if __name__ == '__main__':
    main()

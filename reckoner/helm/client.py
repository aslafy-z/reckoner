from provider import HelmProvider
from command import HelmCommand
from reckoner.command_line_caller import Response
import re
import logging


class HelmClient(object):
    version_regex = re.compile(r'[a-zA-Z]+: v([0-9\.]+)(\+g[0-9a-f]+)?')
    repository_header_regex = re.compile(r'^NAME\s+URL$')
    global_helm_flags = ['debug', 'home', 'host', 'kube-context', 'kubeconfig',
                         'tiller-connection_timeout', 'tiller-namespace']

    def __init__(self, default_helm_arguments=[], provider=HelmProvider):
        self._default_helm_arguments = self._validate_default_helm_args(default_helm_arguments)
        self._provider = provider

    @property
    def default_helm_arguments(self):
        """The default helm arguments for all commands run through the client."""
        return self._default_helm_arguments

    @default_helm_arguments.setter
    def default_helm_arguments(self, value):
        """Setter of the default helm arguments to override"""
        self._default_helm_arguments = value

    def execute(self, command, arguments=[], filter_non_global_flags=False):
        """
        Run the command with the help of the provider.

        return HelmCmdResponse
        """

        default_args = list(self.default_helm_arguments)

        if filter_non_global_flags:
            self._clean_non_global_flags(default_args)

        arguments = default_args + list(arguments)

        command = HelmCommand(
            command=command,
            arguments=arguments,
        )
        response = self._provider.execute(command)
        if response.succeeded:
            return response
        else:
            raise HelmClientException('Command Failed with output below:\nSTDOUT: {}\nSTDERR: {}\nCOMMAND: {}'.format(
                response.stdout, response.stderr, response.command))

    @property
    def client_version(self):
        return self._get_version('--client')

    @property
    def server_version(self):
        return self._get_version('--server')

    @property
    def repositories(self):
        repository_names = []
        raw_repositories = self.execute('repo', ['list'], filter_non_global_flags=True).stdout
        for line in raw_repositories.splitlines():
            # Try to filter out the header line as a viable repo name
            if HelmClient.repository_header_regex.match(line):
                continue
            # If the line is blank
            if not line:
                continue

            repository_names.append(line.split()[0])

        return repository_names

    def check_helm_command(self):
        return self.execute("help", [], filter_non_global_flags=True).succeeded

    def upgrade(self, args, install=True):
        if install:
            arguments = ['--install'] + args
        else:
            arguments = args
        return self.execute("upgrade", arguments)

    def rollback(self, release):
        raise NotImplementedError(
            '''This is known bad. If you see this error then you are likely implementing the solution :)'''
        )

    def dependency_update(self, chart_path):
        raise NotImplementedError('Sorry this feature has not yet been implemented.')

    def repo_update(self):
        """Function to update all the repositories"""
        return self.execute('repo', ['update'], filter_non_global_flags=True)

    def repo_add(self, name, url):
        """Function add repositories to helm via command line"""
        return self.execute('repo', ['add', name, url], filter_non_global_flags=True)

    @staticmethod
    def _clean_non_global_flags(list_of_args):
        """Return a copy of the set arguments without any non-global flags - do not edit the instance of default_helm_args"""
        # Filtering out non-global helm flags -- this is to try and support
        # setting all-encompassing flags like `tiller-namespace` but avoiding
        # passing subcommand specific flags to commands that don't support
        # them.
        # Example: `helm upgrade --install --recreate-pods ...` but we don't
        #          want to run `helm repo add --recreate-pods repo-name ...`
        #
        # TODO: This is a slow implementation but it's fine for cli (presumably)
        #       Bad nesting - there's a better pattern for sure
        #
        # Looping logic:
        #   1. run through each argument in defaults
        #   2. Set known global false for item's iteration
        #   3. For each item in defaults check if it matches a known good global argument
        #   4. if matches note it, set known good = true and break inner iteration
        #   5. if inner iter doesn't find global param then known_global is bad and delete it from list
        for arg in list_of_args:
            logging.debug('Processing {} argument'.format(arg))
            known_global = False
            for valid in HelmClient.global_helm_flags:
                if re.findall("--{}(\s|$)+".format(valid), arg):
                    known_global = True
                    break  # break out of loop and stop searching for valids for this one argument
            if known_global:
                logging.debug('This argument {} was found in valid arguments: {}, keeping in list.'.format(arg, ' '.join(HelmClient.global_helm_flags)))
            else:
                list_of_args.remove(arg)
                logging.debug('This argument {} was not found in valid arguments: {}, removing from list.'.format(arg, ' '.join(HelmClient.global_helm_flags)))

    def _get_version(self, kind='--server'):
        get_ver = self.execute("version", arguments=['--short', kind], filter_non_global_flags=True)
        ver = self._find_version(get_ver.stdout)

        if ver == None:
            raise HelmClientException(
                """Could not find version!! Could the helm response format have changed?
                STDOUT: {}
                STDERR: {}
                COMMAND: {}""".format(get_ver.stdout, get_ver.stderr, get_ver.command)
            )

        return ver

    @staticmethod
    def _find_version(raw_version):
        ver = HelmClient.version_regex.search(raw_version)
        if ver:
            return ver.group(1)
        else:
            return None

    @staticmethod
    def _validate_default_helm_args(helm_args):
        # Allow class to be instantiated with default_helm_arguments to be None
        if helm_args is None:
            helm_args = []

        # Validate that we're providing an iterator for default helm args
        if not hasattr(helm_args, '__iter__'):
            logging.error("This class is being instantiated without an iterator for default_helm_args.")
            raise ValueError('default_helm_arguments needs to be an iterator')

        return helm_args


class HelmClientException(Exception):
    pass

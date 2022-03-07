settings_path = '/etc/axiom/settings.json'
site_db = 'axiomWebserver/site.db'
configurator_output_path = '/etc/axiom/configurator_output.json'
consumption_db_name = 'consumption.db'

OUTPUT_CMD_CHANNEL = 'axiomLogic:cmd:state'
OUTPUT_INFO_CHANNEL = 'axiomLogic:info:state'
INPUT_CMD_CHANNEL = 'axiomWebserver:cmd:state'
INPUT_INFO_CHANNEL = 'axiomLowLevelCommunication:info:state'
CREATE_JOB_CHANNEL = 'axiomWebserver:schedule:create'
DELETE_JOB_CHANNEL = 'axiomWebserver:schedule:delete'
UPDATE_JOB_CHANNEL = 'axiomWebserver:schedule:update'
JOBS_DB_NAME = 'jobs.sqlite'
LOG_FILE_NAME = '_axiomLogic.log'
LOG_FILE_DIRECTORY = '/var/log/axiom'
CONFIGURATION_FILES_PATH = '/etc/axiom'
CONFIGURATION_FILE_NAME = 'nodes_configuration.json'
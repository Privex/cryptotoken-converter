#!/usr/bin/env bash
#########################################################################
#                                                                       #
#                   Production runner script for:                       #
#                                                                       #
#                       CryptoToken Converter                           #
#                (C) 2019 Privex Inc.   GNU AGPL v3                     #
#                                                                       #
#      Privex Site: https://www.privex.io/                              #
#                                                                       #
#      Github Repo: https://github.com/Privex/cryptotoken-converter     #
#                                                                       #
#########################################################################

set -eE

# Load or install Privex ShellCore library
_sc_fail() { >&2 echo "Failed to load or install Privex ShellCore..." && exit 1; }
[[ -f "${HOME}/.pv-shcore/load.sh" ]] || [[ -f "/usr/local/share/pv-shcore/load.sh" ]] || \
    { curl -fsS https://cdn.privex.io/github/shell-core/install.sh | bash >/dev/null; } || _sc_fail

[[ -d "${HOME}/.pv-shcore" ]] && source "${HOME}/.pv-shcore/load.sh" || \
    source "/usr/local/share/pv-shcore/load.sh" || _sc_fail

######
# Directory where the script is located, so we can source files regardless of where PWD is
######

! [ -z ${ZSH_VERSION+x} ] && _SDIR=${(%):-%N} || _SDIR="${BASH_SOURCE[0]}"
DIR="$( cd "$( dirname "${_SDIR}" )" && pwd )"
cd "$DIR"
[[ -f .env ]] && source .env || echo "Warning: No .env file found."

export PATH="${HOME}/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:${PATH}"

# Override these defaults inside of `.env`
: ${HOST='127.0.0.1'}
: ${PORT='8009'}
: ${GU_WORKERS='8'}    # Number of Gunicorn worker processes
: ${GU_TIMEOUT='600'}

_run_help() {
    msg bold green "Privex CryptoToken-Converter - (C) 2019 Privex Inc."
    msg bold green "    Website: https://www.privex.io/"
    msg bold green "    Source: https://github.com/Privex/cryptotoken-converter\n"
    msg green "Available run.sh commands:\n"
    msg yellow "\t cron - Quietly update BGP prefixes from GoBGP"
    msg yellow "\t update - Upgrade your Privex CryptoToken-Converter installation"
    msg yellow "\t server - Start the production Gunicorn server"
    msg green "\nAdditional aliases for the above commands:\n"
    msg yellow "\t upgrade - Alias for 'update'"
    msg yellow "\t serve, runserver - Alias for 'server'"
    msg
}

(($#<1)) && _run_help && exit 1

case "$1" in
    load*)
        msg ts bold green "Loading CTC Deposits..."
        pipenv run ./manage.py load_txs
        ;;
    convert*)
        msg ts bold green "Processing CTC conversions..."
        pipenv run ./manage.py convert_coins
        ;;
    cron*)
        if [[ ! -f "${DIR}/.crons.txt" ]]; then
            msg ts yellow "Did not find '.crons.txt' - copying defaults from '.crons.txt.example'"
            cp -v "${DIR}/.crons.txt.example" "${DIR}/.crons.txt"
        fi
        msg ts bold green "Running all crons listed in '.crons.txt' in parallel"
        parallel --will-cite -j2 < "${DIR}/.crons.txt"
        ;;
    migrate)
        pipenv run ./manage.py migrate
        ;;
    createsuperuser)
        pipenv run ./manage.py createsuperuser
        ;;
    update|upgrade)
        msg ts bold green " >> Updating files from Github"
        git pull
        msg ts bold green " >> Updating Python packages"
        pipenv update
        msg ts bold green " >> Migrating the database"
        pipenv run ./manage.py migrate
        msg ts bold green " +++ Finished"
        echo
        msg bold yellow "Post-update info:"
        msg yellow "Please **become root**, and read the below additional steps to finish your update"

        msg yellow " - You may wish to update your systemd service files in-case there are any changes:"
        msg blue "\t cp -v *.service /etc/systemd/system/"
        msg blue "\t systemctl daemon-reload"

        msg yellow " - Please remember to restart any CryptoToken-Converter services AS ROOT like so:"
        msg blue "\t systemctl restart ctc"
        ;;
    serve*|runserv*|prod*)
        pipenv run gunicorn --timeout "$GU_TIMEOUT" -b "${HOST}:${PORT}" -w "$GU_WORKERS" steemengine.wsgi
        ;;
    dev*)
        pipenv run ./manage.py runserver
        ;;
    *)
        msg bold red "Unknown command.\n"
        _run_help
        ;;
esac

msg

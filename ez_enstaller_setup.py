#------------------------------------------------------------------------------
# Copyright (c) 2007, Enthought, Inc.
# All rights reserved.
#
# This software is provided without warranty under the terms of the BSD license
# available at http://www.enthought.com/licenses/BSD.txt and may be
# redistributed only under the conditions described in the aforementioned
# license.
#
# Rick Ratzel - 2006-06-27
#------------------------------------------------------------------------------
#
# The default repository
#
ENTHOUGHT_REPO = "http://code.enthought.com/enstaller/eggs"

import sys
import os
import types
import time
import re
import urllib
from os import path
from optparse import OptionParser
from tempfile import gettempdir
from getpass import getuser
from traceback import extract_tb
from urlparse import urljoin

IS_WINDOWS = sys.platform.lower().startswith( "win" )
#
# some Python distros (on Suse, others?) do not have the distutils std library
# module and instead package it in a separate python-devel package which is not
# installed by default.  Since distutils is required by setuptools and
# Enstaller, inform the user that they have a "broken" Python.
#
if( __name__ == "__main__" ) :
    try :
        import distutils

    except ImportError :
        err_msg = """
        Could not import distutils!  This is required to run Enstaller and is
        normally part of the Python standard library.\n"""

        if( not( IS_WINDOWS ) ) :
            err_msg += """
        Some Linux distributions provide a minimal Python install for their own
        purposes which does not have a complete standard library.  The remaining
        Python components may be found in a separate "python-devel" package,
        depending on your distribution.\n"""

        err_msg += """
        Please ensure that you are using an install of Python with a complete
        standard library and try again.\n\n"""

        sys.stderr.write( err_msg )
        sys.exit( 1 )

from distutils.sysconfig import get_python_lib

PYVER = "%s.%s" % (sys.version_info[0], sys.version_info[1])

################################################################################
####  TextIO
####
####  A mixin class that adds basic text-based I/O functionality.
####
####  These functions will most likely be used elsewhere in Enstaller.  They
####  provide methods for logging output messages and reading user input.  The
####  logging methods assume a logging_handle has been set (usually sys.stdout)
####  which has standard file object methods.
################################################################################
class TextIO( object ) :
    """
    A mixin which provides methods for logging output messages and reading user
    input.  The methods assume a logging_handle has been set (usually
    sys.stdout) has standard file object methods.
    """

    def __init__( self, logging_handle=sys.stdout,
                  verbose=False, prompting=True ) :
        #
        # the logging_handle must be an object with at least a write
        # and flush method
        #
        self.logging_handle = logging_handle
        self.verbose = verbose
        self.prompting = prompting


    def debug( self, msg ) :
        """
        Log msg if self.verbose == True.
        """
        if( self.verbose ) :
            self.log( msg )


    def log( self, msg ) :
        """
        Writes msg to the logging handle, if set.
        """
        if( not( self.logging_handle is None ) ) :
            self.logging_handle.write( msg )


    def prompt( self, prompt_text, default_response ) :
        """
        Prints the prompt_text and reads stdin if the prompt_flag is True.  If
        the flag is False, returns the default_response.  If the
        default_response is a bool, the input read is y/n, yes/no, etc. and is
        converted to a bool...if default_response is a string, response is
        converted to a string, etc.
        """
        response = None
        expected_type = type( default_response )
        
        if( self.prompting ) :
            while( response is None ) :
                raw_response = self.prompter( prompt_text ).strip()
                #
                # boolean
                #
                if( expected_type == types.BooleanType ) :
                    if( raw_response.lower() in ["y", "yes"] ) :
                        response = True
                    elif( raw_response.lower() in ["n", "no"] ) :
                        response = False
                #
                # number
                #
                elif( expected_type == types.IntType ) :
                    if( raw_response.isdigit() ) :
                        response = int( raw_response )
                #
                # string
                #
                else :
                    response = raw_response
        else :
            response = default_response

        return response


    def prompter( self, msg ) :
        """
        Prints message and returns user input...meant to be overridden if the
        launcher is not used from a console.
        """
        self.log( msg )
        return raw_input()


################################################################################
####  URLUtil
####  
####  Wraps various urllib functions with exception handlers to gracefully
####  handle timeouts, etc.
####  
################################################################################
class URLUtil( TextIO ) :
    """
    Class to gracefully handle timeouts, etc. for urllib functions.
    """

    retries_on_timeout = 2

    retry_msg = "Timed out accessing %s...retrying.\n"
    
    bad_url_warning = "Warning: URL %s could not be opened.\n" + \
                      "The error was: %s\n" + \
                      "This URL will not be used.\n"

    too_many_retries = "Operation timed out %s times while trying to " + \
                       "access URL %s.\nThis URL will not be used.\n"
    
    successful_read_msg = "Successfully read %s\n"

    #
    # Set to True if the wrapper is to re-raise bad URL exceptions instead of
    # logging them (will still retry on timeouts)
    #
    reraise_on_bad_urls = False
    
    
    def urlopen( self, url ) :
        """
        Calls urllib.urlopen() on the URL, handling bad URLs and timeouts.
        """
        #
        # urllib.urlopen does not accept file:// (???)
        #
        if( re.match( "^file://", url, re.IGNORECASE ) ) :
            url = url[7:]
            
        return self._urllib_wrapper( urllib.urlopen, url )


    def urlretrieve( self, url, dest=None, reporthook=None ) :
        """
        Calls urllib.urlretrieve() on the URL, handling bad URLs and timeouts.
        """
        return self._urllib_wrapper( urllib.urlretrieve, url, dest, reporthook )
    

    def _urllib_wrapper( self, func, url, *args ) :
        """
        Calls urllib functions which take a url as the first arg, handling
        errors gracefully and retries on timeouts.
        """
        retval = None
        retries = 0
        err = ""
        
        while( retries < self.retries_on_timeout ) :
            try :
                retval = apply( func, ((url, ) + args) )
                #
                # Print a confirmation if the URL had to be retried.
                #
                if( retries > 0 ) :
                    self.log( self.successful_read_msg % url )
                break
            
            except IOError, err :
                #
                # Check for timeout, all other socket errs are bad URLs
                #
                socket_err = ""
                if( err.args[0] == "socket error" ) :
                    socket_err = err.args[1].args[1]

                if( socket_err == "Operation timed out" ) :
                    self.log( self.retry_msg % url )
                    retries += 1
                    continue

                if( self.reraise_on_bad_urls ) :
                    raise
                else :
                    self.log( self.bad_url_warning % (url, err) )
                    break
        #
        # Print a message if the max retries has been exceeded.
        #
        if( retries >= self.retries_on_timeout ) :
            self.log( self.too_many_retries % (url, self.retries_on_timeout+1) )
            
        return retval


################################################################################
####  Downloader
####  
####  Downloads files from a URL or local path to a destination directory.
####  
####  Provides features for finding the latest version, or specific versions
####  of files from a local or remote repository and downloading them to a
####  target directory.  Methods for reporting the download progress are also
####  defined and overridable for different UIs.
################################################################################
class Downloader( TextIO ) :
    """
    Class containing a minimum set of utility functions for accessing packages
    from a repository.
    """

    use_cached_file_prompt = "Use the cached file eventhough the size could " + \
                             "not be verified (download may not even be " + \
                             "possible otherwise) (y/n)?"

    def __init__( self, *args, **kwargs ) :
        """
        Setup some bookkepping vars, primarily for the download meter and a
        URLUtil instance for accessing URLs.
        """
        super( Downloader, self ).__init__( *args, **kwargs )
        
        self._filename_width = 32
        self._screen_width = 79 # needs to be actual screen width - 1 for Windows
        self._download_filename = ""
        self._download_starttime = 0.0
        self._download_fraction = 0.0

        self._urlutil = URLUtil( *args, **kwargs )
        

    def download_file( self, src_url, dest_dir, clobber=False ) :
        """
        Downloads or copies a file from a url to a destination dir and returns
        the path to the newly downloaded/copied file.
        If clobber is set to True, will download even if the file exists.
        """
        self._download_filename = path.basename( src_url )
        self._download_starttime = 0.0
        self._download_fraction = 0.0
        #
        # support Windows and use file:/// since a drive letter might be present
        #
        if( path.exists( src_url ) and IS_WINDOWS ) :
            src_url = "file:///%s" % src_url
            
        dest_path = path.join( dest_dir, self._download_filename )

        if( clobber or not( self.file_downloaded( src_url, dest_dir ) ) ) :

            self.log( "Downloading: %s\n" % src_url )
            self._download_report_init()
            self._download_starttime = time.time()

            ok = self._urlutil.urlretrieve( src_url, dest_path,
                                            self._download_report_progress )
            if( ok is None ) :
                raise RuntimeError, "Problem downloading %s" % src_url
            
            self._download_report_fini()

        else :
            self.log( "%s has already been downloaded" % src_url + \
                      "...skipping download.\n" )
        
        return dest_path


    def file_downloaded( self, src_url, dest_dir ) :
        """
        Returns True if the src_url has been downloaded to the dest_dir and
        *appears* to be the same (based on size, if available), otherwise False.
        """
        retval = False
        dest_path = path.join( dest_dir, path.basename( src_url ) )
        
        if( path.exists( dest_path ) ) :
            retval = True
            #
            # assume file is good, but check size if possible
            #
            statinfo = os.stat( dest_path )
            size_on_disk = statinfo.st_size
            #
            # If the URL is bad, download may not even be possible, so prompt the
            # user if they want to use the cached file at their own risk
            # (defaults to no).
            #
            url = self._urlutil.urlopen( src_url )
            if( url is None ) :

                self.log( "Cannot verify that the cached file is valid.\n" )
                if( not( self.prompt( self.use_cached_file_prompt, False ) ) ) :
                    retval = False
                else :
                    retval = True

            else :
                headers = url.info()

                if( headers.has_key( "content-length" ) ) :
                    if( long( headers["content-length"] ) != size_on_disk ) :
                        self.log( "File: %s exists, but is not " % dest_path + \
                                  "the expected size.\n" )
                        retval = False

                url.close()
                
        return retval
    
        
    def find_latest_version( self, find_links, src_file_patt ) :
        """
        Returns a tuple containg the version number and the complete url to the
        latest version of a file matching the pattern from all the urls in
        find_links.  Returns None if a file matching the pattern was not found.
        """
        if( type( find_links ) != types.ListType ) :
            find_links = [find_links]

        results = {}
        #
        # Assume the find_links are in order of preference, and since the
        # results are stored in a dictionary with versions as keys, any
        # same-versioned results will be stored as "last one wins"...so, reverse
        # the list so matching versions are taken from earlier urls in the list.
        #
        repos = find_links[:]
        repos.reverse()
        for repo in repos :
            self.debug( "Checking %s\n" % repo )
            (version, url) = self._find_latest_version( repo, src_file_patt )
            if( not( url is None ) ) :
                results[version] = url
        #
        # return the highest version url in the dict, if present
        #
        versions = results.keys()
        if( versions ) :
            versions.sort( self.version_cmp )
            return results[versions[-1]]

        return None


    @staticmethod
    def get_site_packages_dir() :
        """
        returns the path to this interps default install location
        (site-pacakges)
        """
        try :
            return path.normcase( path.normpath( get_python_lib() ) )
        except :
            raise RuntimeError, \
                  "could not find default install location (site-packages)"


    def make_cache( self, name="__enstaller_tmp" ) :
        """
        Creates a cache directory in the location specified, named after
        name then the username (if available).
        """
        location = gettempdir()
        try :
            username = getuser()
        except :
            username = ""
            
        cache = path.abspath( path.join( location, name + "_%s" % username ) )
        if( not( path.exists( cache ) ) ) :
            try :
                os.mkdir( cache )
            except :
                self.log( "Could not create cache directory: %s" % cache + \
                          "...quitting." )
                sys.exit( 1 )

        return cache


    @staticmethod
    def version_cmp( a, b ) :
        """
        Function used in comparisons on strings which represent version numbers.
        """
        a_greater = 1
        b_greater = -1
        number_letter_patt = re.compile( "([0-9]+)([a-zA-Z]?)" )
        rev_number_patt = re.compile( "[Rr][Ee]?[Vv]?([0-9]+)" )
        #
        # Return 0 if versions are equal
        #
        if( a == b ) :
            return 0
        #
        # Compare each number in the version individually by splitting on .
        #
        a_vers = re.split( "[\.\_]", a )
        b_vers = re.split( "[\.\_]", b )
        #
        # Only compare the shortest length of numbers
        #
        for i in range( min( len( a_vers ), len( b_vers ) ) ) :
            #
            # Try to compare numbers, if that fails, compare strings
            #
            try :
                a = int( a_vers[i] )
                b = int( b_vers[i] )
            except ValueError :
                a = a_vers[i]
                b = b_vers[i]
                #
                # special case if a number has a single letter after it...if the
                # numbers are equal, the version with no letter is higher.
                #
                matcha = number_letter_patt.match( a )
                matchb = number_letter_patt.match( b )
                if( matcha and matchb ) :
                    a_parts = matcha.groups()
                    b_parts = matchb.groups()
                    if( a_parts[0] == b_parts[0] ) :
                        if( a_parts[1] == "" ) : return a_greater
                        if( b_parts[1] == "" ) : return b_greater
                #
                # special case if the number is a rev number, extract the number
                #
                matcha = rev_number_patt.match( a )
                matchb = rev_number_patt.match( b )
                if( matcha and matchb ) :
                    a = int( matcha.group( 1 ) )
                    b = int( matchb.group( 1 ) )

            if( a > b ) :
                return a_greater
            elif( b > a ) :
                return b_greater
        #
        # If still equal at this point, the version string lengths must be
        # unequal so longer of the two is assumed to be greater.
        #
        if( len( a_vers ) > len( b_vers ) ) :
            return a_greater

        else :
            return b_greater


    def _download_report_fini( self ) :
        """
        Called at the end of a download...in this case, it is used to write the
        total download time to stdout.
        """
        #
        # Do this only if the logging_handle is the real stdout or if its an
        # EnstallerLogger with no buffering (assume its going to stdout).
        #
        if( (self.logging_handle == sys.__stdout__) or
            (hasattr( self.logging_handle, "copy_to_buffer" ) and
             (self.logging_handle.copy_to_buffer == False)) ) :
            screen = self.logging_handle
        else :
            return

        total_time = time.time() - self._download_starttime
        #
        # backspace 16 times since download time plus | is 16 chars.
        #
        screen.write( "\b" * 16 )
        #
        # compute the time in human-readable form and print
        #
        hours = "%02d" % (total_time / 3600)
        minutes = "%02d" % ((total_time % 3600) / 60)
        secs = ((total_time % 3600) % 60)
        seconds = "%02d.%02d" % (secs, (secs - int( secs )) * 100)
        screen.write( "| %sh:%sm:%ss" % (hours, minutes, seconds) )
        screen.write( "\n" )
        screen.flush()


    def _download_report_init( self ) :
        """
        Called whenever a download starts...in this case, it is used for
        setting up stdout to print download status.
        """
        #
        # Do this only if the logging_handle is the real stdout or if its an
        # EnstallerLogger with no buffering (assume its going to stdout).
        #
        if( (self.logging_handle == sys.__stdout__) or
            (hasattr( self.logging_handle, "copy_to_buffer" ) and
             (self.logging_handle.copy_to_buffer == False)) ) :
            screen = self.logging_handle
        else :
            return

        fnw = self._filename_width
        name_len = len( self._download_filename )
        #
        # compute the spacing and write the name
        #
        space = max( 0, fnw - name_len )
        screen.write( "%s%s|" % (self._download_filename[0:fnw],
                                 " " * space) )
        #
        # write spaces to the end of the screen, placing the cursor at the end
        #
        screen.write( " " * (self._screen_width - (fnw + 1)) )
        screen.flush()

        
    def _download_report_progress( self, block_cnt, block_size, total_size ) :
        """
        Called periodically as download progresses and is passed the current
        block count, size (bytes) per block, and total size (bytes)...in this
        case, it is used for printing download status to stdout.
        """
        #
        # Do this only if the logging_handle is the real stdout or if its an
        # EnstallerLogger with no buffering (assume its going to stdout).
        #
        if( (self.logging_handle == sys.__stdout__) or
            (hasattr( self.logging_handle, "copy_to_buffer" ) and
             (self.logging_handle.copy_to_buffer == False)) ) :
            screen = self.logging_handle
        else :
            return

        fnw = self._filename_width
        #
        # compute the percentage of the file downloaded
        #
        downloaded_bytes = block_cnt * block_size
        fraction = ((downloaded_bytes * 1.0) / total_size)
        if( fraction > 1 ) :
            fraction = 1
        #
        # compute the space for the stars and write the appropriate number
        # based on the percentage of the file downloaded and the number of
        # stars already on the screen.
        #
        star_space = (self._screen_width - (fnw + 2) - 9)
        num_stars = int( star_space * self._download_fraction )
        num_stars_to_add = int( (star_space * fraction) ) - num_stars
        #
        # backspace all the way back to the end of the existing stars:
        # 9 slots for "| 100.00%", then extra space where stars will go.
        # ...then, write the new stars
        #
        screen.write( "\b" * (9 + (star_space - num_stars)) )

        screen.write( "*" * num_stars_to_add )
        screen.write( " " * (star_space - num_stars - num_stars_to_add) )
        #
        # write the new %...add up to 2 spaces depending if >10%, or >100%
        #
        percent = fraction * 100
        screen.write( "| " )
        if( percent < 10 ) :
            screen.write( "  " )
        elif( percent < 100 ) :
            screen.write( " " )

        screen.write( "%d.%02d%%" % (percent,
                                         (percent - int( percent )) * 100) )
        screen.flush()
        #
        # update the fraction so the next iter knows if it needs more stars
        #
        if( num_stars_to_add > 0 ) :
            self._download_fraction = fraction


    href_patt = re.compile( "\<[Aa]\ +[Hh][Rr][Ee][Ff]\ *=\ *[\"\']([A-Za-z0-9\.\-\_]+)[\"\']\ *\>" )
    
    def _find_latest_version( self, src_url, src_file_patt ) :
        """
        Returns a tuple containg the version number and the complete url to the
        latest version of a file matching the pattern.  Returns a tuple of Nones
        if a file matching the pattern could not be found.

        This is used primarily for find_latest_version(), which takes a list of
        urls and iterates over them, calling this method for each and comparing
        the results to find the overall highest version.
        """
        all_files = []
        versioned_files = {}
        patt_obj = re.compile( src_file_patt )
        #
        # if this is a regular directory, look for matches in the dir listing
        #
        if( src_url.lower().startswith( "file://" ) ) :
            src_url = src_url[7:]
            if( IS_WINDOWS ) :
                src_url = src_url.strip( "/" )

        if( path.exists( src_url ) ) :
            for filename in os.listdir( src_url ) :
                match = patt_obj.match( filename )
                if( match ) :
                    self.debug( "found match: %s\n" % filename )
                    versioned_files[match.group( 1 )] = path.join( src_url,
                                                                   filename )
        #
        # if a url, look for matches in the returned html
        #
        else :
            src_url += "/"
            #
            # Return Nones (as if the request was not found) if the URL was bad
            #
            url = self._urlutil.urlopen( src_url )
            if( url is None ) :
                return (None, None)
            
            http_response = url.read()
            url.close()
            hrefs = self.href_patt.findall( http_response )
            for filename in [path.basename( hr ) for hr in hrefs] :
                match = patt_obj.match( filename )
                if( match ) :
                    self.debug( "found match: %s\n" % filename )
                    versioned_files[match.group( 1 )] = urljoin( src_url,
                                                                 filename )
        #
        # return the highest version
        #
        keys = versioned_files.keys()
        keys.sort( self.version_cmp )
        if( keys ) :
            highest_ver = keys[-1]
            self.debug( "Latest version from %s is: %s\n" \
                        % (src_url, versioned_files[highest_ver]) )
            return (highest_ver, versioned_files[highest_ver])
        else :
            return (None, None)


################################################################################
####  EnstallerLauncher
####
####  Class used to start a standalone Enstaller session.
####
####  The heart of this class is the launch() method which starts a standalone
####  Enstaller session.  If necessary, and permitted by the user, Enstaller is
####  "bootstrapped" (downloaded and installed) prior to starting if it had not
####  been installed before.
################################################################################
class EnstallerLauncher( TextIO ) :
    """
    Class used to start a standalone Enstaller session.
    """
    #
    # The postmortem file...if a crash occurs, send this file to the authors
    #
    postmortem_file = path.abspath( "ENSTALLER_POSTMORTEM.txt" )
    #
    # the Enstaller egg name pattern to match.
    # Note the $ at the end...needed to avoid matching things like foo.egg.info
    #
    enstaller_egg_name = "enstaller-(.*)-py%s.*\.egg$" % PYVER
    #
    # Output messages
    #
    enstaller_import_error = """
The Enstaller package could not be imported...this means Enstaller is not
installed or is broken or missing (need to set PYTHONPATH?)
"""

    install_enstaller_prompt = """
Proceed to download and install Enstaller? (y/n) """

    bootstrapping_enstaller = """
Attempting to download the Enstaller package...
"""

    enstaller_egg_not_found = """
An Enstaller egg for this Python version was not found!
Use the --find-links option to specify a URL which has an Enstaller egg
for Python version %s
""" % PYVER

    unknown_option_msg = """
Enstaller does not appear to be installed and the option "%s"
is not recognized...it is either invalid or requires the complete Enstaller
package to be processed.  The options available at this time are:

"""


    def __init__( self, *args, **kwargs ) :
        """
        Construct with an optional logging_handle (must support file methods
        write() and flush()) used for outputting messages to the user.
        """
        super( EnstallerLauncher, self ).__init__( *args, **kwargs )
        #
        # assign defaults to attributes
        # (overridden when command-line is processed
        #
        self.argv = []
        self.gui = True
        self.install_dir = ""
        self.find_links = []
        self.bootstrap = True
        #
        # setup a file downloader
        #
        self.downloader = Downloader( logging_handle=self.logging_handle,
                                      verbose=self.verbose,
                                      prompting=self.prompting )
        

    def bootstrap_bootstrap( self ) :
        """
        Downloads the latest Enstaller egg to a temp directory to access its
        bootstrap code, where the bootstrap code will then handle the formal
        installation of Enstaller and all necessary dependencies.

        The egg in the temp dir is added to the current sys.path, the bootstrap
        module is imported from it and ran, then the temp egg is "unimported"
        and removed.
        """
        self.log( self.bootstrapping_enstaller )
        #
        # get the URL for the Enstaller egg...this may involve asking the user
        # which version they want.
        #
        url = self.get_enstaller_url()
        #
        # open a temp file to save the egg contents to...it will be installed
        # properly at the end of the bootstrap process
        #
        cache = self.downloader.make_cache()
        egg = self.downloader.download_file( url, cache )
        #
        # import the bootstrap code from the temporary egg and run it
        #
        sys.path.insert( 0, egg )
        from enthought.enstaller.bootstrapper import Bootstrapper
        bs = Bootstrapper( self.find_links, self.gui,
                           logging_handle=self.logging_handle,
                           verbose=self.verbose,
                           prompting=self.prompting )

        try :
            bs.bootstrap( self.install_dir, egg )
        except AssertionError :
            sys.exit( 1 )
        #
        # "unimport" the temporary egg since it may be deleted from disk
        # (assumed to be properly installed at this point)
        #
        sys.path.remove( egg )
        allmods = sys.modules.keys()
        for mod in allmods :
            if( mod.startswith( "enstaller" ) and (mod in sys.modules.keys()) ) :
                del sys.modules[mod]


    @staticmethod
    def build_option_parser( program_name=sys.argv[0],
                             opt_parser_class=OptionParser ) :
        """
        Returns a basic option parser which supports options primarily used for
        bootstrapping Enstaller.  Other Enstaller operations defined in the
        Enstaller egg will add to the option parser returned by this function.
        """
        usage = "USAGE: %prog [options]"
        #
        # Add a new link only if it has not been added before.
        #
        def add_link( option, opt_str, value, parser ) :
            if( len( parser.rargs ) > 0 ) :
                arg = parser.rargs[0]
                if( not( arg.startswith( "-" ) ) ) :
                    if( not( arg in parser.values.find_links ) ) :
                        parser.values.find_links.append( arg )
                    del parser.rargs[0]

        opt_parser = opt_parser_class( prog=program_name, usage=usage,
                                       version=VERSION_STRING )

        opt_parser.add_option( "-c", "--command-line",
                               dest="gui", default=True,
                               action="store_false",
                               help="do not use/install the Enstaller GUI" )

        opt_parser.add_option( "-d", "--install-dir",
                               dest="install_dir", metavar="<dir>",
                               default="",
                               help="use an alternate directory to install" + \
                               "packages to (defaults to site-packages for" + \
                               "use by all users)" )

        opt_parser.add_option( "-f", "--find-links",
                               dest="find_links", metavar="<repo>",
                               default=[],
                               action="callback", callback=add_link,
                               help="add a package repository URL to the " + \
                               "search list" )

        opt_parser.add_option( "-n", "--no-bootstrap",
                               dest="bootstrap", default=True,
                               action="store_false",
                               help="do not attempt to bootstrap Enstaller" )

        opt_parser.add_option( "-t", "--batch",
                               dest="prompting", default=True,
                               action="store_false",
                               help="batch mode - do not confirm operations" + \
                               "(command-line only)" )

        opt_parser.add_option( "-v", "--verbose",
                               dest="verbose",default=False,
                               action="store_true",
                               help="print debug-level messages" )

        opt_parser.add_option( "--no-default-enthought-repo",
                               dest="use_default_enthought_repo", default=True,
                               action="store_false",
                               help="do not use the Enthought repository " + \
                               "by default" )

        #
        # Override the optparse check_values method in order to add the default
        # Enthought repo last in the order of find_links precedence, if it is to
        # be used at all.
        #
        def check_values( values, args ) :
            find_links = values.find_links
            use_def_en_repo = values.use_default_enthought_repo
            if( use_def_en_repo and not( ENTHOUGHT_REPO in find_links ) ) :
                find_links.append( ENTHOUGHT_REPO )
            return (values, args)
            
        opt_parser.check_values = check_values
        
        return opt_parser


    def get_enstaller_url( self ) :
        """
        Returns a URL to the latest compatible Enstaller egg.
        """
        #
        # add the default repo to any user-specified repos and look for the
        # highest known-compatible Enstaller egg...warn user if not found
        #
        enstaller_url = None
        find_links = self.find_links[:]

        self.debug( "Looking for a known compatible egg...\n" )
        enstaller_url = self.downloader.find_latest_version(
            find_links, self.enstaller_egg_name )
        #
        # if a URL could not be determined, abort
        #
        if( enstaller_url is None ) :
            self.log( self.enstaller_egg_not_found )
            sys.exit( 1 )
            
        return enstaller_url


    def launch( self, argv ) :
        """
        Launches the app, gracefully handling any uncaught exceptions.
        """
        try :
            retcode = self.run( argv )

        except SystemExit, code:
            retcode = code
        
        except Exception, err:
            pm_text = self._write_postmortem()
            self.debug( pm_text )
            retcode = 1

        return retcode


    def run( self, argv, bootstrapping=False ) :
        """
        Runs the "main" function in the Enstaller package used to start a
        standalone session of Enstaller.

        An attempt to import the Enstaller package is made, and if that is
        successful Enstaller is started.  If it could not be imported and the
        user has not disabled bootstrapping, the latest Enstaller egg is
        downloaded and the bootstrap process defined in that egg is run.
        """
        #
        # without processing the args, check for the verbose flag for debugging
        #
        if( ("-v" in argv) or ("--verbose" in argv) ) :
            self.verbose = True

        #
        # If Enstaller is installed, set the version info and pass the command
        # line args to the main function.
        #
        try :
            from enthought.enstaller.main import main
            return main( argv, self.logging_handle )

        #
        # If this point is reached Enstaller is not installed (or is broken).
        # Use the arg processor in this script to examine the command line and
        # determine the next action (bootstrap, print traceback, etc.)
        #
        except ImportError, err :
            #
            # read the command line, continue only if its valid
            #
            args_ok = self._process_command_line( argv )
            if( args_ok != 0 ) :
                return args_ok
            #
            # bootstrap Enstaller--if permitted--by installing the latest
            # Enstaller egg and using its bootstrap module and call run() again.
            #
            if( not( bootstrapping ) ) :
                self.log( self.enstaller_import_error )
                self.log( "\nThe import error was: %s\n" % err )

                if( self.bootstrap ) :
                    if( self.prompt( self.install_enstaller_prompt, True ) ) :
                        self.bootstrap_bootstrap()                    
                        return self.run( argv, bootstrapping=True )
                    else :
                        return 1
            #
            # if this point is reached, there is a bug.
            #
            elif( bootstrapping ) :
                self.log( "\nAn error was encountered while " + \
                          "bootstrapping Enstaller!\n" )

            raise


    def _process_command_line( self, argv ) :
        """
        Read the command line and set attributes on this object.
        """
        logging_handle = self.logging_handle
        unknown_option_msg = self.unknown_option_msg
        #
        # For parsing options for the bootstrap operation, override the error
        # handler to print a message explaining that unknown options may be valid
        # once Enstaller is installed, but not recognized with this opt parser.
        #
        class TempOptParser( OptionParser ) :
            def error( self, msg ) :
                exit_msg = ""
                if( msg.startswith( "no such option: " ) ) :
                    bad_opt = msg.split( ": " )[1]
                    logging_handle.write( unknown_option_msg % bad_opt )
                else :
                    exit_msg = "%s: error: %s\n" % (self.get_prog_name(), msg)

                self.print_help( logging_handle )
                self.exit( 2, exit_msg )

        opt_parser = self.build_option_parser( argv[0], TempOptParser )

        #
        # prevent OptionParser from shutting down the app
        #
        try :
            args_obj = opt_parser.parse_args( args=argv )[0]

        except SystemExit, return_code :
            return return_code

        self.argv = argv
        self.gui = args_obj.gui
        self.install_dir = args_obj.install_dir
        self.find_links = args_obj.find_links
        self.bootstrap = args_obj.bootstrap
        self.prompting = args_obj.prompting
        self.verbose = args_obj.verbose
        #
        # update the downloader with the new options
        #
        self.downloader.prompting = self.prompting
        self.downloader.verbose = self.verbose

        return 0
    

    def _write_postmortem( self ) :
        """
        Formats the last exception in "postmortem text" and writes it to the
        postmortem file for bug reporting.  Returns the pm_text.
        """
        #
        # create the pm text
        #
        (exc, msg, tb) = sys.exc_info()
        self.log( "\nInternal Error: %s: %s\n\n" % (exc, msg) )
        
        pm_text = "Error: %s\n" % msg
            
        for (filename, lineno, funcname, text) in extract_tb( tb ) :
            pm_text += "  File %s, line %s, in %s\n" \
                       % (filename, lineno, funcname)
            pm_text += "     %s\n" % text
        pm_text += "\n"
        #
        # Extra info for the file
        #
        header = "*" * 79 + "\n"
        header += "* Time of death: %s\n" % time.asctime()
        header += "* Command line: %s\n" % sys.argv
        header += "* Python executable: %s\n" % sys.executable
        header += "* Python version: %s\n" % sys.version
        header += "*" * 79 + "\n"
        #
        # write the file
        #
        try :
            pm_file = open( self.postmortem_file, "a" )
            pm_file.write( header + pm_text )
            pm_file.close()
            self.log( "Please submit the following postmortem file to the " + \
                      "authors:\n%s\n\n" % self.postmortem_file )

        except :
            sys.stderr.write( "\nAn internal error occurred and a postmortem " +\
                              "file could not be written!\n" )
            sys.stderr.write( "Here is the postmortem text:\n %s" % pm_text )

        return pm_text


    
################################################################################
#### "main" for running as a script.
################################################################################
if( __name__ == "__main__" ) :
    launcher = EnstallerLauncher()
    ret_code = launcher.launch( sys.argv )
    sys.exit( ret_code )

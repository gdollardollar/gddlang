#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import unicodedata
import re
# from xml.sax.saxutils import escape as xml_escape
import itertools
import csv
import argparse


global __showwarnings, __showinfo

def loginfo(str):
    """Utility function to log information"""
    if __showinfo:
        print(str)

def logwarning(str):
    """Utility function to log warnings"""
    if __showwarnings:
        print('Warning: '+str)

class LangError(Exception):
    """Base class for exception created by this script"""

    def prefix(cls):
        return 'Error'

    def __str__(self):
        return self.prefix() + ': '+ super(LangError, self).__str__()

class LangParseError(LangError):
    """Class for exception found while parsing"""

    def prefix(cls):
        return 'ParseError'

class LanguageElement:
    """Class encapsulating the key of the string and the different values."""

    # regex used to properly strip "pretty" (with repeated *) multiline comments
    pc_pattern = re.compile(r'^[ \t\f\v]*\*?[ \t\f\v]*(.*)$',re.MULTILINE)

    def __init__(self, key='', comment=''):
        """Keyword Arguments:

        key    -- The string key. Must not be None, must be normalized.
        values -- A list containing the different values"""
        self.key = key
        self.values = {}
        self.comment = "\n".join(self.pc_pattern.findall(comment.strip()))

    #regex used to normalize keys
    #TODO:  Normalizing keys is not a good idea because people might use 
    #       accents in their string keys and this will then change the 
    #       key in the output...
    key_pattern = re.compile('[^\w\s_]+')
    @classmethod
    def normalizekey(cls, key):
        """Normalizes keys between android and ios"""
        u = unicodedata.normalize('NFKD', unicode(key, 'utf-8'))
        formattedKey = u.encode('ascii', 'ignore')
        return cls.key_pattern.sub(' ', formattedKey)

    def getvalue(self, language):
        """Getter for string value

        Keyword Arguments:
        language -- the language your want the value for"""
        try:
            return self.values[language]
        except KeyError, IndexError:
            return None

    def setvalue(self, language, value):
        """setter for string value

        Keyword Arguments:
        language -- the language the value is for
        value    -- the value"""
        assert self.key, 'Tried to set a value {} without a key'.format(value)
        if value:
            self.values[language] = value

    def csv_columns(self, languages):
        """Convernience method that returns a generator 
        representing the string for a csv line"""
        a = [self.comment, self.key, ]
        a.extend(((self.getvalue(l) or '') for l in languages))
        return a

    # def androidline(self, language):
    #     """Returns a string corresponding to the android line for the language

    #     Keyword arguments:
    #     languageIndex --  the language index (defaults to 0)
    #     """
    #     formattedKey = self.key.replace(' ', '_')
    #     formattedValue = xml_escape(self.values[language])
    #     return '<string name="{}">{}</string>'.format(formattedKey, formattedValue)

    def cocoa_line(self, language):
        """Convenience method that returns a string corresponding 
        to the cocoa line for the provided language

        Keyword arguments:
        language -- the language
        """
        value = self.getvalue(language)
        if value:
            value = value.replace('"', '\\"') #todo:replace with regex
        else:
            value = ''
        commentstring = None
        if '\n' in self.comment:
            commentstring = '/*\n * ' + self.comment.replace('\n','\n * ') + '\n */'
        elif self.comment:
            commentstring = '// ' + self.comment

        line = ''
        if self.key:
            line += '"{}" = "{}";'.format(self.key, value)
        if commentstring:
            line += commentstring
        return line

    def __str__(self):
        return str({ 'key' : self.key, 'values' : self.values, 'comment' : self.comment })

class LanguageResource:
    """Represents the Language Resources.
    I-e several strings and several languages"""

    def __init__(self):
        # an array containing the languages
        self.languages = []
        # an array containing the LanguageElement instances
        # it is repeated in keyedelements so that they can be accessed quickly
        self.elements = []
        self.keyedelements = {}

    def reset(self):
        """Deletes all the resources"""
        self.languages = []
        self.elements = []
        self.keyedelements = {}

    # Convenience

    def getlanguages(self):
        return self.languages

    def getkeyedelement(self, key):
        """Returns the element corresponding to the provided key

        Keyword arguments:
        key -- the key"""
        try:
            return self.keyedelements[key]
        except KeyError, IndexError:
            return None

    def getvalue(self, key, language):
        """Returns the value corresponding to the provided key and language

        Keyword arguments:
        key      -- the key
        language -- the language"""
        try:
            return self.keyedelements[key].getvalue(language)
        except KeyError, IndexError:
            return None

    def missingvalues(self):
        """Returns the array of the elements that are missing values 
        in a language"""
        missing = { l : [] for l in self.languages}
        for k,v in self.keyedelements.iteritems():
            for l in self.languages:
                if not v.getvalue(l):
                    missing[l].append(k)
        #There might a more efficient way to cleanup?
        for k in missing.keys():
            if not missing[k]:
                del missing[k]
        return missing

    # Base construction

    def __insertcomment(self, comment, index=None):
        """ Inserts a comment, returns True if a new element was created

        Keyword arguments:
        comment -- a comment string
        index   -- the index at which the comment should be inserted, defaults to end of elements array.
        """
        # This is probably not optimized
        if index == None:
            index = len(self.elements)
        self.elements.insert(index, LanguageElement(comment=comment))
        return index

    def __insertstring(self, key, string, comment, language, index=None):
        """ Inserts a new string, returns True if a new element was created.
        Raises a LangParseError if a value already exists for the corresponding key.

        Keyword arguments:
        key      -- the string key (str)
        string   --  a string (str)
        language -- the language
        index    -- the desired position, if the key was already present, then it is ignored"""
        # This is probably not optimized
        if index == None:
            index = len(self.elements)

        key = LanguageElement.normalizekey(key)
        element = self.getkeyedelement(key)
        if element:
            if element.getvalue(language):
                raise LangParseError("Value already exists for key '{}' and language '{}'".format(key, language))
            index = self.elements.index(element)
        else:
            element = LanguageElement(key=key)
            self.elements.insert(index, element)
            self.keyedelements[key] = element
        element.setvalue(language, string)
        return index

    def __constructelement(self, key, value, comment, language, usecomments = True, index=None):
        """Constructs and inserts a string element
        Returns the index of the inserted object

        Keyword arguments:
        key         -- the key
        value       -- the value
        comment     -- a comment, can be None
        language    -- the language
        usecomments -- if false the comment is ignored, defaults to True
        index       -- the preferred insertion index, defaults to None"""
        if key:
            try:
                return self.__insertstring(key, value, (usecomments and comment) or '', language, index=index) 
            except LangParseError as e:
                print(e)
                return index
        elif usecomments and comment:
            return self.__insertcomment(comment, index=index)
        else:
            return index

    def __constructelements(self, key, languagevaluedic, comment, usecomments = True, index = None):
        """Constructs and inserts a string element given a value dictionary,
        The element will contain the languages and values present in the 
        provided language-value dictionary
        Returns the index of the inserted object.
        Used mostly when creating elements from a csv file.

        Keyword arguments:
        key              -- the keyindex
        languagevaluedic -- a language-value dictionary containing all the values for the string
        usecomments      -- if false the comment is ignored, defaults to True
        index            -- the preferred insertion index, defaults to None"""
        if key and languagevaluedic:
            for l,v in languagevaluedic.iteritems():
                # index won't change since we are adding values to the same key
                index = self.__constructelement(key=key, value=v, comment=comment, language=l, usecomments=usecomments, index=index)
                # deleting comment so that it is not added twice
                comment = None
                usecomments = None
            return index
        else:
            return self.__constructelement(key=None, value=None, comment=comment, language=None, usecomments=usecomments, index=index)

    # Cocoa reading

    def cocoa_feed(self, path, languages=None, tablename=None, usecomments=True, autocorrect=None):
        """Creates all elements from a provided path, interpreting cocoa files.
        Path can be:
        - a directory containing .lproj directory
        - a .lproj directory (the languages argument will be ignored, 
            and the name of the directory will be used instead)
        - a .strings file (in which case the language must be provided)
        This method checks which kind of path it is and then calls the appropriate method

        Keyword arguments:
        path        -- the path
        languages   -- the languages, defaults to None in which case the array will be determined automatically
        tablename   -- the table name (e.g Localizable in Localizable.strings). Defaults to None, i-e all tables will be considered
        usecomments -- if False the comments are ignored, defaults to True
        autocorrect -- if None the user will be prompted in conflicts, 
                       if True the conflicts will be autocorrected, 
                       if False the conflicts will be ignored"""
        if os.path.isfile(path) and path.endswith('.strings'):
            language = None
            if languages:
                language = languages[0]
                if len(languages) > 1:
                    logwarning('Too many languages specified for .strings file. Only considering first one i-e ' + language)
            self.cocoa_feedstrings(filepath=path, language=language, usecomments=usecomments, autocorrect=autocorrect)
        elif os.path.isdir(path) and path.endswith('.lproj'):
            self.cocoa_feedlproj(path=path, tablename=tablename, usecomments=usecomments, autocorrect=autocorrect)
        elif os.path.isdir(path):
            self.cocoa_feeddir(path=path, languages=languages, tablename=tablename, usecomments=usecomments, autocorrect=autocorrect)
        else:
            raise LangError('Invalid path: ' + path)

    def cocoa_feeddir(self, path, languages=None, tablename=None, usecomments=True, autocorrect=None):
        """Creates all elements from a provided directory path, interpreting cocoa files.
        The directory must contain .lproj directories and not be a .lproj dir itself (see cocoa_feedlproj for that).
        Calls cocoa_feedlproj with the right paths.
        Returns autocorrect (which can change depending on the user's response to prompts)

        Keyword arguments:
        path        -- the path
        languages   -- if provided, restricts the .lproj directory that are considered
        tableName   -- the table name (e.g Localizable in Localizable.strings). Defaults to None, i-e all tables will be considered
        usecomments -- if False the comments are ignored, defaults to True
        autocorrect -- if None the user will be prompted in conflicts, 
                       if True the conflicts will be autocorrected, 
                       if False the conflicts will be ignored"""
        assert os.path.isdir(path) and not path.endswith('.lproj'), 'Incorrect dir path ' + path

        if languages:
            dirs = list((os.path.join(path,p) for p in os.listdir(path) if p.endswith('.lproj') and p[:-6] in languages))
            if not dirs:
                raise LangError('Directory {} did not contain any lproj dir for the specified languages {}'.format(path, languages))
        else:
            dirs = list((os.path.join(path,p) for p in os.listdir(path) if p.endswith('.lproj')))
            if not dirs:
                raise LangError('Directory {} did not contain any lproj dir'.format(path))

        for lprojpath in dirs:
            autocorrect = self.cocoa_feedlproj(path=lprojpath, tablename=tablename, usecomments=usecomments, autocorrect=autocorrect)
            usecomments = False
        return autocorrect

    def cocoa_feedlproj(self, path, tablename=None, usecomments=True, autocorrect=None):
        """Creates all elements from a provided .lproj directory path, interpreting cocoa files.
        Calls cocoa_feedstrings with the right paths.
        Returns autocorrect (which can change depending on the user's response to prompts)

        Keyword arguments:
        path        -- the path
        tableName   -- the table name (e.g Localizable in Localizable.strings). Defaults to None, i-e all tables will be considered
        usecomments -- if False the comments are ignored, defaults to True
        autocorrect -- if None the user will be prompted in conflicts, 
                       if True the conflicts will be autocorrected, 
                       if False the conflicts will be ignored"""
        assert path.endswith('.lproj') and os.path.isdir(path), 'Incorrect lproj path ' + path
        language = os.path.basename(path)[:-6]
        if tablename:
            stringpath = os.path.join(path, tablename + '.strings')
            if os.path.isfile(stringpath):
                return self.cocoa_feedstrings(stringpath, language, usecomments, autocorrect)
            else:
                logwarning('File did not exist at path ' + stringpath)
                return autocorrect
        else:
            files = (os.path.join(path,p) for p in os.listdir(path) if p.endswith('.strings'))
            for stringpath in files:
                if usecomments:
                    self.__insertcomment('======================\nTable : ' + os.path.basename(stringpath)[:-8] + '\n======================')
                autocorrect = self.cocoa_feedstrings(stringpath, language, usecomments, autocorrect)

            return autocorrect

    @classmethod
    def cocoa_getlinepattern(cls):
        # regex to parse a line of a strings file
        # groups are :
        #   key (<key> or None)
        #   value (<value> or None)
        #   sc (; or None)
        #   com (// <comment> or /* <comment> or None)
        return re.compile(r'''  (?: # Beginning of key/value block or value block
                                    (?: # Beginning of key block
                                        ((?<![\\])[\'"])                    # unescaped quote or single quote and stores it in 1
                                        (?P<key>(?:.(?!(?<![\\])\1))*.?)    # key
                                        \1                                  # quote found in 1
                                        \s*?=\s*?
                                    )?  # End of key block
                                    ((?<![\\])[\'"])                      # same as before but stored in 3
                                    (?P<val>(?:.(?!(?<![\\])\3))*.?)      # value
                                    \3
                                )?  # End of key/value block or value block
                                \s*?
                                (?P<sc>;{1})?                               # semicolon?
                                [\s|;]*?
                                (?:(?P<com>[//|/*].*))?
                                $'''          # comment?
                                ,re.VERBOSE)

    def cocoa_feedstrings(self, filepath, language=None, usecomments=True, autocorrect=None):
        """Parses a cocoa .strings file and stores its values

        Only supported schemes are (ignoring white spaces):

        "key" = "value"; // comment

        "key" = "value"; /* comment */

        "key" = "value" // comment
                "value2" // comment
                ..
                "value"; // comment

        /* Multiline comment
        ..
        ..
        */

        // Comment

        Returns autocorrect.

        Keyword arguments:
        filepath -- the .strings file path
        language -- the language associated with the file
        """
        try:
            if usecomments and not language is self.languages[0]:
                logwarning('Ignoring comments from file at path '+ filepath)
                usecomments = False
        except IndexError:  # if it fails, it means that there are no languages and therefore no need to warn 
            pass

        if not language:
            parentdir = os.path.dirname(filepath)
            if parentdir.endswith('.lproj'):
                language = os.path.basename(parentdir)[:-6]
                logwarning('Assuming language is ' + language)
            else:
                raise LangError("Language was not provided")

        cocoa_pattern = self.cocoa_getlinepattern()

        with open(filepath, 'r') as f:

            if not language in self.languages:
                self.languages.append(language)

            # Initializing variables
            (key, value, comment, multilinecomment, consume) = ('', '', '', False, False)
            (tempkey, tempvalue, tempcomment, tempterm) = (None, None, None, False)
            index = -1
            lastinsertindex = len(self.elements)-1

            for line in f:
                # construct element and reset
                if consume: 
                    lastinsertindex = self.__constructelement(key, value, comment, language, usecomments, lastinsertindex+1)
                    (key, value, comment, multilinecomment, consume) = ('', '', '', False, False)

                # Ignoring empty lines
                line = line.strip()
                if not line:  
                    continue

                # Handling multiline comments
                if multilinecomment:
                    index = line.find('*/')
                    if index >= 0: #end of multiline comment, boolean reset at beginning of loop
                        comment += ((index > 0 and '\n') or '') + line[:index]
                        consume = True
                        if len(line) > index + 2:
                            logwarning('Ignoring line after "*/": "{}"'.format(line[index+2:]))
                    else:
                        comment += '\n' + line
                    continue

                # Using regex
                m = cocoa_pattern.match(line)
                if m:
                    (tempkey, tempvalue, tempcomment, tempterm) = ( m.group('key'), m.group('val'), m.group('com'), m.group('sc')!=None )

                    # Handling value and key
                    if tempkey:  # Expecting value

                        # Checking for conflict
                        if key:  
                            (autocorrect, lastinsertindex) = self.__cocoa_handlecorrection(key, value, comment, language, usecomments, autocorrect, lastinsertindex+1)
                            (key, value, comment, multilinecomment, consume) = ('', '', '', False, False)

                        if tempvalue == None:
                            logwarning('ignoring line because it had a key but not a value:\n    {}'.format(line))
                            continue
                        else:
                            (key, value, consume) = (tempkey, tempvalue, tempterm)
                            consume = tempterm  # Consuming only if ; was present 
                    else:
                        if tempvalue != None:
                            if key:
                                value += tempvalue
                                consume = tempterm
                            else:
                                logwarning('ignoring line because it had a value but no key was set:\n    {}'.format(line))
                                continue

                    # Handling comment
                    if tempcomment: # Ignoring empty comments
                        # Checking if comment is multiline
                        if tempcomment.startswith('/*'):
                            index = tempcomment.find('*/')
                            if index >= 0:
                                tempcomment = tempcomment[:index]
                            else:
                                multilinecomment = True
                        else: # Single line comment
                            if not ( key or value ):
                                consume = True
                        # Removing first comment char
                        if comment:
                            comment += '; ' + tempcomment[2:].strip()
                        else:
                            comment = tempcomment[2:].strip()

                else:
                    logwarning('ignoring line because regex did not match:\n    {}'.format(line))
                    continue

            # Dealing with last line
            if consume:
                self.__constructelement(key, value, comment, language, usecomments, lastinsertindex+1)
            elif key and value:
                (autocorrect, lastinsertindex) = self.__cocoa_handlecorrection(key, value, comment, language, usecomments, autocorrect, lastinsertindex+1)

        return autocorrect

    def __cocoa_handlecorrection(self, key, value, comment, language, usecomments, autocorrect, index):
        """Returns (autocorrect, insertindex)"""
        if autocorrect == None:
            i = raw_input('Cocoa parse error (You probably forgot a ;):\n'\
                          '    key = "{}"\n'\
                          '    value = "{}"\n'
                          'Should I still add it?\n'
                          'y(yes), ya(yes to all), n(no), na(no to all)\n'.format(key, value))
            ia = ('y','n','ya','na')
            while i not in ia:
                i = raw_input('What do you mean ?\n')

            if i == 'ya':
                autocorrect = True
            elif i == 'na':
                return (False, index)
            elif i == 'n':
                return (None, index)

        # Resolving
        logwarning('adding from parse error key = {}, value = {}'.format(key, value))
        index = self.__constructelement(key, value, comment, language, usecomments, index)

        return (autocorrect, index)

    # Cocoa writing

    def __cocoa_string(self, language, pretty = False):
        """Returns the corresponding cocoa string
        """
        s = "\n".join((item.cocoa_line(language) for item in self.elements))
        if pretty:
            s = re.sub('$\s*?(?=/)','\n\n',s,flags=re.MULTILINE)
        return s

    def cocoa_write(self, languages=None, path='.', overwrite=False, tablename='Localizable', pretty = False):
        """Writes the resources in the corresponding lproj directories
        e.g with the default arguments, the en file will be written to en.lproj/Localizable.strings

        Keyword Arguments:
        languages --  the chosen languages. If none is provided, all languages are created. Defaults to None.
        path -- the directory in which the .lproj directories will be written. Defaults to '.'
        tablename -- the tableName, i-e the name of the strings file. Defaults to 'Localizable'
        """
        if os.path.exists(path) and not os.path.isdir(path):
            raise LangError('Output path {} is not a directory'.format(path))

        if not languages:
            languages = self.languages
        
        if len(languages)>1:
            for l in self.languages:
                self.cocoa_write([l], path, overwrite, tablename, pretty)
        else:
            language = languages[0]
            dirpath = os.path.join(path,language + os.path.extsep + "lproj")
            if not os.path.exists(dirpath):
                os.makedirs(dirpath)
            outputpath = os.path.join(dirpath, tablename + os.path.extsep + "strings")
            if os.path.exists(outputpath) and not overwrite:
                raise LangError('File already exists at path %s' % outputpath)

            s = self.__cocoa_string(language, pretty)
            loginfo('Writing cocoa file at path '+outputpath)
            with  open(outputpath, 'w') as f:
                f.write(s)

    # Csv reading

    @classmethod
    def __csv_parsefirstrow(cls, row, languages, usecomments):
        """Returns (keyindex, commentindex, langindices)
        """
        (keyindex, commentindex, langindices) = (None, None, {})
        # Getting key
        try:
            keyindex = row.index('key')
        except IndexError:
            raise LangError('Could not find key column in csv')
        # Getting comment
        if usecomments:
            try:
                commentindex = row.index('comment')
            except IndexError:
                logwarning('Could not find comment column in csv')
        # Getting languages
        for c in row:
            if not c in ('key','comment'):
                if languages and c not in languages:  # ignoring if not in languages
                    continue
                langindices[c] = row.index(c)

        return (keyindex, commentindex, langindices)

    def __csv_feedrow(self, row, keyindex, commentindex, langindices, index):
        # Getting key
        try:
            key = row[keyindex]
        except IndexError:
            key = None
        # Getting value
        values = {}
        for l in self.languages:
            try:
                values[l] = row[langindices[l]]
            except KeyError, IndexError:  # Either language not present in file (language may come from another file), or column not present in row
                values[l] = ''
        # Getting comment
        if commentindex == None:
            comment = None
        else:
            try:
                comment = row[commentindex]
            except IndexError:
                comment = None

        return self.__constructelements(key=key, languagevaluedic=values, comment=comment, index=index)

    # Csv writing

    def csv_feed(self, path, languages=None, usecomments=True):
        with open(path, 'rb') as csvfile:
            reader = csv.reader(csvfile, delimiter=';', quotechar='"')
            
            (keyindex, commentindex, langindices) = (None, None, {})
            lastinsertindex = len(self.elements)-1
            for row in reader:
                if keyindex == None:  # First row
                    (keyindex, commentindex, langindices) = self.__csv_parsefirstrow(row, languages, usecomments)

                    for l in langindices.keys():
                        if l not in self.languages:
                            self.languages.append(l)

                    if not self.languages:
                        e = 'Did not find any language in file ' + path
                        if languages:
                            e += 'with language filter ' + str(languages)
                        raise LangError(e)
                else:  # Any other row
                    lastinsertindex = self.__csv_feedrow(row=row, keyindex=keyindex, commentindex=commentindex, langindices=langindices, index=lastinsertindex+1)

    def csv_write(self, path='languages.csv', overwrite=False):
        """Writes a csv file containing all the info
        """
        if not overwrite:
            if os.path.exists(path):
                raise LangError('File already existed at path "{}"'.format(path))

        loginfo('Writing csv file at path '+path)

        with open(path, 'wb') as csvfile:
            writer = csv.writer(csvfile, delimiter=';', quotechar='"', quoting=csv.QUOTE_ALL)
            writer.writerow(['comment','key', ] + self.languages)
            for element in self.elements:
                writer.writerow(element.csv_columns(self.languages))

    # Info

    def printinfo(self, details=False):
        print('\n==================\n'\
              ' Info\n')
        print('Languages: ' + str(self.languages))
        print('String count: ' + str(len(self.keyedelements)))
        # Calculating missing keys
        if self.languages and len(self.languages)>1:
            missing = self.missingvalues()
            if missing:
                if details:
                    print('Missing values:')
                    for k,v in missing.iteritems():
                        print('   {} : {}'.format(k, v))
                else:
                    print('Missing value count:')
                    for k,v in missing.iteritems():
                        print('   {} : {}'.format(k, len(v)))
            else:
                print('No missing value')

        print('==================\n')

# Main

if __name__ == '__main__':

    __loginfo = True

    default_outdir = '~/Desktop'
    default_outandroid = os.path.join(default_outdir, 'strings.xml')
    default_outios = os.path.join(default_outdir, 'strings')
    default_outcsv = os.path.join(default_outdir, 'languages.csv')

    parser = argparse.ArgumentParser(prog='gddlang',description='Converts back and forth between csv, android or cocoa langauge files.', epilog='xoxo')
    parser.add_argument('paths', help='Input paths.', type=str, nargs='+')
    parser.add_argument('--no_warning', help='Disable warnings', action='store_true', default=False)
    parser.add_argument('--no_comments', help='Disable comments', action='store_true', default=False)
    parser.add_argument('--auto_correct', help='Consider conflicts? If not specified, you will be prompted if some happen', type=bool, choices=[True,False], default=None)
    parser.add_argument('-l', '--languages', help='Language filter', nargs='+', type=str)
    parser.add_argument('--silent', help='Only outputs error', action='store_true', default=False)
    # Input
    inputs = parser.add_argument_group(title='Input')
    inputargs = inputs.add_mutually_exclusive_group(required=True)
    inputargs.add_argument('-a', help='Input is android.', action='store_true')
    inputargs.add_argument('-c', help='Input is csv. Expecting .csv file with first line : [comment] | keys | language1 | language2 ....', action='store_true')
    inputargs.add_argument('-i', help='Input is cocoa. Path can either be a folder containing lproj dirs, an lproj dir or a .strings file', action='store_true')
    # Output
    outputs = parser.add_argument_group(title='Output')
    outputs.add_argument('--info', help='Do not print info. 0=No info 1=Default 2=Details.', default=1, type=int, choices=[0,1,2])
    outputs.add_argument('-A', help='Output android. If no path is provided, {} is used.'.format(default_outandroid), nargs='?', type=str, const=default_outandroid)
    outputs.add_argument('-C', help='Output csv. If no path is provided, {} is used'.format(default_outcsv), nargs='?', type=str, const=default_outcsv)
    outputs.add_argument('-I', help='Output cocoa. If no path is provided, {} is used'.format(default_outios), nargs='?', type=str, const=default_outios)
    outputs.add_argument('-f', '--force', help='Overwrite', action='store_true')
    outputs.add_argument('-p', '--pretty', help='Try to increase prettyness of output files', action='store_true')

    args = parser.parse_args()

    if args.silent:
        __showinfo = False
        __showwarnings = False
    elif args.no_warning:
        __showinfo = True
        __showwarnings = False
    else:
        __showinfo = True
        __showwarnings = True

    res = LanguageResource()

    for path in args.paths:
        path=os.path.expanduser(path)

        if not os.path.exists(path):
            print('Error: could not find file at path '+path)

        if args.a:
            print('Android input is not yet supported')
            exit()
        elif args.c:
            res.csv_feed(path=path, languages=args.languages, usecomments=not args.no_comments)
        elif args.i:
            res.cocoa_feed(path=path, languages=args.languages, usecomments=not args.no_comments, autocorrect=args.auto_correct)

    if args.info == 1:
        res.printinfo(False)
    elif args.info == 2:
        res.printinfo(True)        

    if not res.getlanguages():
        exit()

    if args.A:
        print('Android output is not yet supported')
    if args.C:
        try:
            res.csv_write(path=os.path.expanduser(args.C), overwrite=args.force)
        except LangError as e:
            print(e)
    if args.I:
        try:
            res.cocoa_write(path=os.path.expanduser(args.I), pretty=args.pretty, overwrite=args.force)
        except LangError as e:
            print(e)

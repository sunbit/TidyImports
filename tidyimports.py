import sublime, sublime_plugin
from SublimeLinter.lint import persist
from collections import OrderedDict
import re


def importStatementParser(text):
    regex = r'^((?P<commented>\s*#+\s*)?(?:from +(?P<from>[\w\-\.]+) +)?import +(?:(?:(?P<package>[\w\-\.]+) +as +(?P<aspackage>[\w\-\.]+))|(?:(?P<packages>[\w\-\.\,\ ]+))))'
    match = re.match(regex, text)
    if match is None:
        return []

    gr = match.groupdict()

    if gr['from'] is not None:
        import_line = 'from {from} import {package}'
    else:
        import_line = 'import {package}'

    if gr['package'] is not None:
        packages = [gr['package'], ]
    else:
        packages = gr['packages'].replace(' ','').split(',')

    if gr['aspackage'] is not None:
        import_line += ' as {aspackage}'

    results = []
    for package in packages:
        params = {}
        params.update(gr)
        params['package'] = package
        results.append({
            'commented': gr['commented'],
            'statement': import_line.format(**params),
            'type': 'package' if gr['from'] is not None else 'module'
        })
    return results


class TidyImports(object):
    def prettify_imports(self, edit):

        # Extract current buffer text and split in lines
        full_view_region = sublime.Region(0, self.view.size())
        text = self.view.substr(full_view_region)
        lines = text.split('\n')

        first_import = None
        last_import = None
        
        # selects all import statements found in text
        # Identifies following formats:
        #   - import x
        #   - from x import y
        #   - from x import y as z
        #   - from x import y,z
        #   - # commented import statement
        #   - non commented import MUST start at beginning of line

        # Search for import statements, blank lines and commented lines
        # until anything else is found

        parsed_imports = {
            'module': [],
            'package': []
        }
        for line_no, line in enumerate(lines):
            match = importStatementParser(line)
            if match:
                for newline in match:
                    if first_import is None:
                        first_import = line_no
                    last_import = line_no

                    parsed_imports[newline['type']].append(newline)
            elif line.strip() == '' or line.strip().startswith('#'):
                last_import = line_no
            else:
                break

        # Calculate begin and start character position of imports block
        # and store it to import_text. Store positions for further replacement
        pre_import_text = '\n'.join(lines[:first_import])
        imports_start = len(pre_import_text)
        import_text = '\n'.join(lines[first_import:last_import + 1])
        imports_end = imports_start + len(import_text)
        imports_region = sublime.Region(imports_start, imports_end)

        # import grouping definitions
        sort_groups_regex = [
            r'zope|Products\.Five|five|Acquisition|AccessControl|z3c\.|App\.|OFS\.',
            r'plone|Products\.CMFCore|Products\.CMFPlone'
        ]


        # group import blocks into groups
        grouped_blocks = OrderedDict([(regex, []) for regex in sort_groups_regex])
        remaining = []

        for block in parsed_imports['package']:
            matched = False
            for regex in sort_groups_regex:
                if re.search(regex, block['statement']):
                    grouped_blocks[regex].append('{}{}'.format('# ' if block['commented'] else '', block['statement']))
                    matched = True
                if matched:
                    break
            if not matched:
                remaining.append('{}{}'.format('# ' if block['commented'] else '', block['statement']))

        # Add remaining and single import blocks to groups
        grouped_blocks['remaining'] = remaining
        grouped_blocks['single'] = ['{}{}'.format('# ' if block['commented'] else '', block['statement']) for block in parsed_imports['module']]

        # Put together groups, sorted alphabetically, including commented ones.
        replacements = []
        for regex, blocks in grouped_blocks.items():
            if blocks:
                sorted_blocks = sorted(blocks, key=lambda block: block.lstrip('#').lstrip(' '))
                replacements.append('\n'.join(sorted_blocks))

        # Separate groups with a blank line
        replacement = '\n\n'.join(replacements)
        replacement = '\n' + replacement + '\n'

        self.view.replace(edit, imports_region, replacement)

    def remove_unused_imports(self, edit):

        # Extract current buffer text and split in lines
        full_view_region = sublime.Region(0, self.view.size())
        lines = self.view.lines(full_view_region)

        # Iterate trough SublimeLinter error lines in reverse, to be able to make 
        # replacements without altering text buffer positions
        list_reversed = [a for a in persist.errors[self.view.id()].items()][::-1]

        for error_line_num, errors in list_reversed:
            error_line_region = lines[error_line_num]
            error_line = self.view.substr(error_line_region)
            new_line = str(error_line)
            replace = False
            # For each error found in a line
            for pos, message in errors:
                match = re.search(r"'(.*?)' imported but unused", message)
                if match:
                    # Act only on unused import errors
                    # deleting parcial or full import statement
                    replace = True                    
                    unused_import = match.groups()[0]
                    new_line = re.sub(r',? ?{}'.format(unused_import), '', new_line)
                    if not re.match(r'(?:from +[\w\-\_\.]+ +)?import([\w\-\_\.\, ]+)(?: +as\s+[\w\-\_\.]+)?', new_line):
                        new_line = ''
            if replace:
                # If a change has been made to the line, due a to a unused import,
                # update buffer
                if new_line:
                    new_line += '\n'
                error_line_region = sublime.Region(error_line_region.begin(), error_line_region.end() + 1)
                self.view.replace(edit, error_line_region, new_line)


class PrettifyImportsCommand(sublime_plugin.TextCommand, TidyImports):
    def run(self, edit):
        self.prettify_imports(edit)


class RemoveUnusedImportsCommand(sublime_plugin.TextCommand, TidyImports):
    def run(self, edit):
        self.remove_unused_imports(edit)


class RemoveUnusedAndPrettifyImportsCommand(sublime_plugin.TextCommand, TidyImports):
    def run(self, edit):
        self.remove_unused_imports(edit)
        self.prettify_imports(edit)

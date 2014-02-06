import sublime, sublime_plugin
from SublimeLinter.lint import persist
from collections import OrderedDict
import re


class TidyImports(object):
    def prettify_imports(self, edit):
        full_view_region = sublime.Region(0, self.view.size())
        text = self.view.substr(full_view_region)

        # selects all import statements from the top of the file
        # Identifies following formats:
        #   - import x
        #   - from x import y
        #   - from x import y as z
        #   - from x import y,z
        #   - # commented import statement

        top_imports_regex = r'((?:\s*#+\s*)?(?:from +[\w\-\.]+ +)?import[\w\-\.\, ]+(?: +as\s+[\w\-\.]+)? *\n)'
        imports = [a for a in re.finditer(top_imports_regex, text)]

        imports_start = imports[0].start()
        imports_end = imports[-1].end()
        imports_region = sublime.Region(imports_start, imports_end)

        from_blocks = []
        import_blocks = []
        for import_line in imports:
            multiple = re.match(r'(\s*#+\s*)?from +([\w\-\.]+) +?import([\w\-\.\, ]+)', import_line.group().strip())
            if multiple:
                commented, from_statement, import_statements = multiple.groups()
                commented = '' if commented is None else commented.strip()
                statements = import_statements.replace(' ','').split(',')

                for statement in statements:
                    from_blocks.append('{}from {} import {}'.format('# ' if commented else '', from_statement, statement))
            else: 
                import_blocks.append(import_line.group().strip())


        sort_groups_regex = [
            r'zope|five|Acquisition|AccessControl|z3c\.',
            r'plone|Products\.CMFCore|Products\.CMFPlone'
        ]

        grouped_blocks = OrderedDict([(regex, []) for regex in sort_groups_regex])
        remaining = []

        for block in from_blocks:
            matched = False
            for regex in sort_groups_regex:
                if re.search(regex, block):
                    grouped_blocks[regex].append(block)
                    matched = True
                if matched:
                    break
            if not matched:
                remaining.append(block)


        grouped_blocks['remaining'] = remaining
        grouped_blocks['single'] = import_blocks

        replacement = ''
        for regex, blocks in grouped_blocks.items():
            if blocks:
                sorted_blocks = sorted(blocks, key=lambda block: block.lstrip('#').lstrip(' '))
                replacement += '\n'.join(sorted_blocks)
                replacement += '\n\n'

        self.view.replace(edit, imports_region, replacement[:-1])

    def remove_unused_imports(self, edit):

        full_view_region = sublime.Region(0, self.view.size())
        lines = self.view.lines(full_view_region)

        list_reversed = [a for a in persist.errors[self.view.id()].items()][::-1]

        for error_line_num, errors in list_reversed:
            error_line_region = lines[error_line_num]
            error_line = self.view.substr(error_line_region)
            new_line = str(error_line)
            replace = False
            for pos, message in errors:
                match = re.search(r"'(.*?)' imported but unused", message)
                if match:
                    
                    replace = True                    
                    unused_import = match.groups()[0]
                    new_line = re.sub(r',? ?{}'.format(unused_import), '', new_line)
                    if not re.match(r'(?:from +[\w\-\.]+ +)?import([\w\-\.\, ]+)(?: +as\s+[\w\-\.]+)?', new_line):
                        new_line = ''
            if replace:
                if new_line:
                    new_line += '\n'
                error_line_region = sublime.Region(error_line_region.begin(), error_line_region.end() + 1)
                self.view.replace(edit, error_line_region, new_line)

MARK_KEY_FORMAT = 'sublimelinter-{}-marks'

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

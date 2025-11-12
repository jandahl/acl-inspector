module.exports = grammar({
  name: 'fortios',

  extras: $ => [
    /\s/,                // skip whitespace
    $.comment            // skip comments
  ],

  rules: {
    source_file: $ => repeat($._statement),

    _statement: $ => choice(
      $.config_block,
      $.edit_block,
      $.set_cmd,
      $.unset_cmd,
      $.get_cmd,
      $.show_cmd
    ),

    // Config block: starts with 'config <object>' and ends with 'end'
    config_block: $ => seq(
      'config', repeat1($.identifier),
      repeat($._config_body_element),
      'end'
    ),

    _config_body_element: $ => choice(
      $.config_block,
      $.edit_block,
      $.set_cmd,
      $.unset_cmd,
      $.get_cmd,
      $.show_cmd
    ),

    // Edit block: starts with 'edit <id>' and ends with 'next'
    edit_block: $ => seq(
      'edit', $.id,
      repeat($._edit_body_element),
      'next'
    ),

    _edit_body_element: $ => choice(
      $.config_block,
      $.set_cmd,
      $.unset_cmd,
      $.get_cmd,
      $.show_cmd
    ),

    // set command: 'set <key> <values...>'
    set_cmd: $ => seq(
      'set', $.identifier, repeat1($.value_part)
    ),

    // unset command: 'unset <key>'
    unset_cmd: $ => seq('unset', $.identifier),

    // get command: 'get <object>'
    get_cmd: $ => seq('get', $.identifier, repeat($.identifier)),

    // show command: 'show <object>'
    show_cmd: $ => seq('show', $.identifier, repeat($.identifier)),

    // Parts of a set value: can be quoted, numeric, or unquoted
    value_part: $ => choice($.multiline_string, $.string, $.number, $.identifier),

    // Identifier token (no spaces or quotes)
    identifier: $ => /[^"\s]+/,

    // Quoted string (single-line)
    string: $ => token(seq('"', /[^"]*/, '"')),

    // Multi-line string (captures until closing quote, for things like certificates)
    multiline_string: $ => token(seq('"', /(?:[\s\S])*?/, '"')),

    // Number (integer)
    number: $ => /\d+/,

    // ID in edit: numeric, quoted, or unquoted
    id: $ => choice($.number, $.string, $.identifier),

    // Full-line comment (skipped as extra)
    comment: $ => token(seq('#', /[^\n]*/))
  }
});

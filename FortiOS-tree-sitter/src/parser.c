#include <tree_sitter/parser.h>

#if defined(__GNUC__) || defined(__clang__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wmissing-field-initializers"
#endif

#define LANGUAGE_VERSION 14
#define STATE_COUNT 56
#define LARGE_STATE_COUNT 7
#define SYMBOL_COUNT 31
#define ALIAS_COUNT 0
#define TOKEN_COUNT 14
#define EXTERNAL_TOKEN_COUNT 0
#define FIELD_COUNT 0
#define MAX_ALIAS_SEQUENCE_LENGTH 4
#define PRODUCTION_ID_COUNT 1

enum {
  anon_sym_config = 1,
  anon_sym_end = 2,
  anon_sym_edit = 3,
  anon_sym_next = 4,
  anon_sym_set = 5,
  anon_sym_unset = 6,
  anon_sym_get = 7,
  anon_sym_show = 8,
  sym_identifier = 9,
  sym_string = 10,
  sym_multiline_string = 11,
  sym_number = 12,
  sym_comment = 13,
  sym_source_file = 14,
  sym__statement = 15,
  sym_config_block = 16,
  sym__config_body_element = 17,
  sym_edit_block = 18,
  sym__edit_body_element = 19,
  sym_set_cmd = 20,
  sym_unset_cmd = 21,
  sym_get_cmd = 22,
  sym_show_cmd = 23,
  sym_value_part = 24,
  sym_id = 25,
  aux_sym_source_file_repeat1 = 26,
  aux_sym_config_block_repeat1 = 27,
  aux_sym_config_block_repeat2 = 28,
  aux_sym_edit_block_repeat1 = 29,
  aux_sym_set_cmd_repeat1 = 30,
};

static const char * const ts_symbol_names[] = {
  [ts_builtin_sym_end] = "end",
  [anon_sym_config] = "config",
  [anon_sym_end] = "end",
  [anon_sym_edit] = "edit",
  [anon_sym_next] = "next",
  [anon_sym_set] = "set",
  [anon_sym_unset] = "unset",
  [anon_sym_get] = "get",
  [anon_sym_show] = "show",
  [sym_identifier] = "identifier",
  [sym_string] = "string",
  [sym_multiline_string] = "multiline_string",
  [sym_number] = "number",
  [sym_comment] = "comment",
  [sym_source_file] = "source_file",
  [sym__statement] = "_statement",
  [sym_config_block] = "config_block",
  [sym__config_body_element] = "_config_body_element",
  [sym_edit_block] = "edit_block",
  [sym__edit_body_element] = "_edit_body_element",
  [sym_set_cmd] = "set_cmd",
  [sym_unset_cmd] = "unset_cmd",
  [sym_get_cmd] = "get_cmd",
  [sym_show_cmd] = "show_cmd",
  [sym_value_part] = "value_part",
  [sym_id] = "id",
  [aux_sym_source_file_repeat1] = "source_file_repeat1",
  [aux_sym_config_block_repeat1] = "config_block_repeat1",
  [aux_sym_config_block_repeat2] = "config_block_repeat2",
  [aux_sym_edit_block_repeat1] = "edit_block_repeat1",
  [aux_sym_set_cmd_repeat1] = "set_cmd_repeat1",
};

static const TSSymbol ts_symbol_map[] = {
  [ts_builtin_sym_end] = ts_builtin_sym_end,
  [anon_sym_config] = anon_sym_config,
  [anon_sym_end] = anon_sym_end,
  [anon_sym_edit] = anon_sym_edit,
  [anon_sym_next] = anon_sym_next,
  [anon_sym_set] = anon_sym_set,
  [anon_sym_unset] = anon_sym_unset,
  [anon_sym_get] = anon_sym_get,
  [anon_sym_show] = anon_sym_show,
  [sym_identifier] = sym_identifier,
  [sym_string] = sym_string,
  [sym_multiline_string] = sym_multiline_string,
  [sym_number] = sym_number,
  [sym_comment] = sym_comment,
  [sym_source_file] = sym_source_file,
  [sym__statement] = sym__statement,
  [sym_config_block] = sym_config_block,
  [sym__config_body_element] = sym__config_body_element,
  [sym_edit_block] = sym_edit_block,
  [sym__edit_body_element] = sym__edit_body_element,
  [sym_set_cmd] = sym_set_cmd,
  [sym_unset_cmd] = sym_unset_cmd,
  [sym_get_cmd] = sym_get_cmd,
  [sym_show_cmd] = sym_show_cmd,
  [sym_value_part] = sym_value_part,
  [sym_id] = sym_id,
  [aux_sym_source_file_repeat1] = aux_sym_source_file_repeat1,
  [aux_sym_config_block_repeat1] = aux_sym_config_block_repeat1,
  [aux_sym_config_block_repeat2] = aux_sym_config_block_repeat2,
  [aux_sym_edit_block_repeat1] = aux_sym_edit_block_repeat1,
  [aux_sym_set_cmd_repeat1] = aux_sym_set_cmd_repeat1,
};

static const TSSymbolMetadata ts_symbol_metadata[] = {
  [ts_builtin_sym_end] = {
    .visible = false,
    .named = true,
  },
  [anon_sym_config] = {
    .visible = true,
    .named = false,
  },
  [anon_sym_end] = {
    .visible = true,
    .named = false,
  },
  [anon_sym_edit] = {
    .visible = true,
    .named = false,
  },
  [anon_sym_next] = {
    .visible = true,
    .named = false,
  },
  [anon_sym_set] = {
    .visible = true,
    .named = false,
  },
  [anon_sym_unset] = {
    .visible = true,
    .named = false,
  },
  [anon_sym_get] = {
    .visible = true,
    .named = false,
  },
  [anon_sym_show] = {
    .visible = true,
    .named = false,
  },
  [sym_identifier] = {
    .visible = true,
    .named = true,
  },
  [sym_string] = {
    .visible = true,
    .named = true,
  },
  [sym_multiline_string] = {
    .visible = true,
    .named = true,
  },
  [sym_number] = {
    .visible = true,
    .named = true,
  },
  [sym_comment] = {
    .visible = true,
    .named = true,
  },
  [sym_source_file] = {
    .visible = true,
    .named = true,
  },
  [sym__statement] = {
    .visible = false,
    .named = true,
  },
  [sym_config_block] = {
    .visible = true,
    .named = true,
  },
  [sym__config_body_element] = {
    .visible = false,
    .named = true,
  },
  [sym_edit_block] = {
    .visible = true,
    .named = true,
  },
  [sym__edit_body_element] = {
    .visible = false,
    .named = true,
  },
  [sym_set_cmd] = {
    .visible = true,
    .named = true,
  },
  [sym_unset_cmd] = {
    .visible = true,
    .named = true,
  },
  [sym_get_cmd] = {
    .visible = true,
    .named = true,
  },
  [sym_show_cmd] = {
    .visible = true,
    .named = true,
  },
  [sym_value_part] = {
    .visible = true,
    .named = true,
  },
  [sym_id] = {
    .visible = true,
    .named = true,
  },
  [aux_sym_source_file_repeat1] = {
    .visible = false,
    .named = false,
  },
  [aux_sym_config_block_repeat1] = {
    .visible = false,
    .named = false,
  },
  [aux_sym_config_block_repeat2] = {
    .visible = false,
    .named = false,
  },
  [aux_sym_edit_block_repeat1] = {
    .visible = false,
    .named = false,
  },
  [aux_sym_set_cmd_repeat1] = {
    .visible = false,
    .named = false,
  },
};

static const TSSymbol ts_alias_sequences[PRODUCTION_ID_COUNT][MAX_ALIAS_SEQUENCE_LENGTH] = {
  [0] = {0},
};

static const uint16_t ts_non_terminal_alias_map[] = {
  0,
};

static const TSStateId ts_primary_state_ids[STATE_COUNT] = {
  [0] = 0,
  [1] = 1,
  [2] = 2,
  [3] = 3,
  [4] = 4,
  [5] = 5,
  [6] = 6,
  [7] = 7,
  [8] = 8,
  [9] = 7,
  [10] = 10,
  [11] = 11,
  [12] = 8,
  [13] = 13,
  [14] = 7,
  [15] = 8,
  [16] = 16,
  [17] = 16,
  [18] = 16,
  [19] = 19,
  [20] = 20,
  [21] = 20,
  [22] = 22,
  [23] = 23,
  [24] = 24,
  [25] = 25,
  [26] = 24,
  [27] = 25,
  [28] = 28,
  [29] = 29,
  [30] = 23,
  [31] = 29,
  [32] = 32,
  [33] = 24,
  [34] = 34,
  [35] = 29,
  [36] = 20,
  [37] = 23,
  [38] = 25,
  [39] = 39,
  [40] = 39,
  [41] = 39,
  [42] = 42,
  [43] = 43,
  [44] = 44,
  [45] = 45,
  [46] = 46,
  [47] = 47,
  [48] = 48,
  [49] = 49,
  [50] = 48,
  [51] = 48,
  [52] = 49,
  [53] = 49,
  [54] = 46,
  [55] = 46,
};

static bool ts_lex(TSLexer *lexer, TSStateId state) {
  START_LEXER();
  eof = lexer->eof(lexer);
  switch (state) {
    case 0:
      if (eof) ADVANCE(30);
      if (lookahead == '"') ADVANCE(4);
      if (lookahead == '#') ADVANCE(70);
      if (lookahead == 'c') ADVANCE(61);
      if (lookahead == 'e') ADVANCE(47);
      if (lookahead == 'g') ADVANCE(50);
      if (lookahead == 'n') ADVANCE(51);
      if (lookahead == 's') ADVANCE(52);
      if (lookahead == 'u') ADVANCE(58);
      if (lookahead == '\t' ||
          lookahead == '\n' ||
          lookahead == '\r' ||
          lookahead == ' ') SKIP(0)
      if (('0' <= lookahead && lookahead <= '9')) ADVANCE(71);
      if (lookahead != 0) ADVANCE(72);
      END_STATE();
    case 1:
      if (lookahead == '"') ADVANCE(4);
      if (lookahead == '#') ADVANCE(70);
      if (lookahead == 'c') ADVANCE(61);
      if (lookahead == 'e') ADVANCE(47);
      if (lookahead == 'g') ADVANCE(50);
      if (lookahead == 's') ADVANCE(52);
      if (lookahead == 'u') ADVANCE(58);
      if (lookahead == '\t' ||
          lookahead == '\n' ||
          lookahead == '\r' ||
          lookahead == ' ') SKIP(1)
      if (('0' <= lookahead && lookahead <= '9')) ADVANCE(71);
      if (lookahead != 0) ADVANCE(72);
      END_STATE();
    case 2:
      if (lookahead == '"') ADVANCE(4);
      if (lookahead == '#') ADVANCE(70);
      if (lookahead == 'c') ADVANCE(61);
      if (lookahead == 'g') ADVANCE(50);
      if (lookahead == 'n') ADVANCE(51);
      if (lookahead == 's') ADVANCE(52);
      if (lookahead == 'u') ADVANCE(58);
      if (lookahead == '\t' ||
          lookahead == '\n' ||
          lookahead == '\r' ||
          lookahead == ' ') SKIP(2)
      if (('0' <= lookahead && lookahead <= '9')) ADVANCE(71);
      if (lookahead != 0) ADVANCE(72);
      END_STATE();
    case 3:
      if (lookahead == '"') ADVANCE(4);
      if (lookahead == '#') ADVANCE(70);
      if (lookahead == '\t' ||
          lookahead == '\n' ||
          lookahead == '\r' ||
          lookahead == ' ') SKIP(3)
      if (('0' <= lookahead && lookahead <= '9')) ADVANCE(71);
      if (lookahead != 0) ADVANCE(72);
      END_STATE();
    case 4:
      if (lookahead == '"') ADVANCE(73);
      if (lookahead == '\t' ||
          lookahead == '\n' ||
          lookahead == '\r' ||
          lookahead == ' ') ADVANCE(4);
      if (lookahead != 0) ADVANCE(5);
      END_STATE();
    case 5:
      if (lookahead == '"') ADVANCE(73);
      if (lookahead != 0) ADVANCE(5);
      END_STATE();
    case 6:
      if (lookahead == 'd') ADVANCE(15);
      if (lookahead == 'n') ADVANCE(7);
      END_STATE();
    case 7:
      if (lookahead == 'd') ADVANCE(33);
      END_STATE();
    case 8:
      if (lookahead == 'e') ADVANCE(21);
      END_STATE();
    case 9:
      if (lookahead == 'e') ADVANCE(27);
      END_STATE();
    case 10:
      if (lookahead == 'e') ADVANCE(22);
      if (lookahead == 'h') ADVANCE(18);
      END_STATE();
    case 11:
      if (lookahead == 'e') ADVANCE(25);
      END_STATE();
    case 12:
      if (lookahead == 'f') ADVANCE(14);
      END_STATE();
    case 13:
      if (lookahead == 'g') ADVANCE(31);
      END_STATE();
    case 14:
      if (lookahead == 'i') ADVANCE(13);
      END_STATE();
    case 15:
      if (lookahead == 'i') ADVANCE(23);
      END_STATE();
    case 16:
      if (lookahead == 'n') ADVANCE(20);
      END_STATE();
    case 17:
      if (lookahead == 'n') ADVANCE(12);
      END_STATE();
    case 18:
      if (lookahead == 'o') ADVANCE(26);
      END_STATE();
    case 19:
      if (lookahead == 'o') ADVANCE(17);
      END_STATE();
    case 20:
      if (lookahead == 's') ADVANCE(11);
      END_STATE();
    case 21:
      if (lookahead == 't') ADVANCE(43);
      END_STATE();
    case 22:
      if (lookahead == 't') ADVANCE(39);
      END_STATE();
    case 23:
      if (lookahead == 't') ADVANCE(35);
      END_STATE();
    case 24:
      if (lookahead == 't') ADVANCE(37);
      END_STATE();
    case 25:
      if (lookahead == 't') ADVANCE(41);
      END_STATE();
    case 26:
      if (lookahead == 'w') ADVANCE(45);
      END_STATE();
    case 27:
      if (lookahead == 'x') ADVANCE(24);
      END_STATE();
    case 28:
      if (eof) ADVANCE(30);
      if (lookahead == '"') ADVANCE(4);
      if (lookahead == '#') ADVANCE(70);
      if (lookahead == 'c') ADVANCE(61);
      if (lookahead == 'e') ADVANCE(48);
      if (lookahead == 'g') ADVANCE(50);
      if (lookahead == 's') ADVANCE(52);
      if (lookahead == 'u') ADVANCE(58);
      if (lookahead == '\t' ||
          lookahead == '\n' ||
          lookahead == '\r' ||
          lookahead == ' ') SKIP(28)
      if (('0' <= lookahead && lookahead <= '9')) ADVANCE(71);
      if (lookahead != 0) ADVANCE(72);
      END_STATE();
    case 29:
      if (eof) ADVANCE(30);
      if (lookahead == '#') ADVANCE(74);
      if (lookahead == 'c') ADVANCE(19);
      if (lookahead == 'e') ADVANCE(6);
      if (lookahead == 'g') ADVANCE(8);
      if (lookahead == 'n') ADVANCE(9);
      if (lookahead == 's') ADVANCE(10);
      if (lookahead == 'u') ADVANCE(16);
      if (lookahead == '\t' ||
          lookahead == '\n' ||
          lookahead == '\r' ||
          lookahead == ' ') SKIP(29)
      END_STATE();
    case 30:
      ACCEPT_TOKEN(ts_builtin_sym_end);
      END_STATE();
    case 31:
      ACCEPT_TOKEN(anon_sym_config);
      END_STATE();
    case 32:
      ACCEPT_TOKEN(anon_sym_config);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 33:
      ACCEPT_TOKEN(anon_sym_end);
      END_STATE();
    case 34:
      ACCEPT_TOKEN(anon_sym_end);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 35:
      ACCEPT_TOKEN(anon_sym_edit);
      END_STATE();
    case 36:
      ACCEPT_TOKEN(anon_sym_edit);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 37:
      ACCEPT_TOKEN(anon_sym_next);
      END_STATE();
    case 38:
      ACCEPT_TOKEN(anon_sym_next);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 39:
      ACCEPT_TOKEN(anon_sym_set);
      END_STATE();
    case 40:
      ACCEPT_TOKEN(anon_sym_set);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 41:
      ACCEPT_TOKEN(anon_sym_unset);
      END_STATE();
    case 42:
      ACCEPT_TOKEN(anon_sym_unset);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 43:
      ACCEPT_TOKEN(anon_sym_get);
      END_STATE();
    case 44:
      ACCEPT_TOKEN(anon_sym_get);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 45:
      ACCEPT_TOKEN(anon_sym_show);
      END_STATE();
    case 46:
      ACCEPT_TOKEN(anon_sym_show);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 47:
      ACCEPT_TOKEN(sym_identifier);
      if (lookahead == 'd') ADVANCE(57);
      if (lookahead == 'n') ADVANCE(49);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 48:
      ACCEPT_TOKEN(sym_identifier);
      if (lookahead == 'd') ADVANCE(57);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 49:
      ACCEPT_TOKEN(sym_identifier);
      if (lookahead == 'd') ADVANCE(34);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 50:
      ACCEPT_TOKEN(sym_identifier);
      if (lookahead == 'e') ADVANCE(63);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 51:
      ACCEPT_TOKEN(sym_identifier);
      if (lookahead == 'e') ADVANCE(69);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 52:
      ACCEPT_TOKEN(sym_identifier);
      if (lookahead == 'e') ADVANCE(64);
      if (lookahead == 'h') ADVANCE(60);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 53:
      ACCEPT_TOKEN(sym_identifier);
      if (lookahead == 'e') ADVANCE(67);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 54:
      ACCEPT_TOKEN(sym_identifier);
      if (lookahead == 'f') ADVANCE(56);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 55:
      ACCEPT_TOKEN(sym_identifier);
      if (lookahead == 'g') ADVANCE(32);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 56:
      ACCEPT_TOKEN(sym_identifier);
      if (lookahead == 'i') ADVANCE(55);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 57:
      ACCEPT_TOKEN(sym_identifier);
      if (lookahead == 'i') ADVANCE(65);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 58:
      ACCEPT_TOKEN(sym_identifier);
      if (lookahead == 'n') ADVANCE(62);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 59:
      ACCEPT_TOKEN(sym_identifier);
      if (lookahead == 'n') ADVANCE(54);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 60:
      ACCEPT_TOKEN(sym_identifier);
      if (lookahead == 'o') ADVANCE(68);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 61:
      ACCEPT_TOKEN(sym_identifier);
      if (lookahead == 'o') ADVANCE(59);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 62:
      ACCEPT_TOKEN(sym_identifier);
      if (lookahead == 's') ADVANCE(53);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 63:
      ACCEPT_TOKEN(sym_identifier);
      if (lookahead == 't') ADVANCE(44);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 64:
      ACCEPT_TOKEN(sym_identifier);
      if (lookahead == 't') ADVANCE(40);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 65:
      ACCEPT_TOKEN(sym_identifier);
      if (lookahead == 't') ADVANCE(36);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 66:
      ACCEPT_TOKEN(sym_identifier);
      if (lookahead == 't') ADVANCE(38);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 67:
      ACCEPT_TOKEN(sym_identifier);
      if (lookahead == 't') ADVANCE(42);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 68:
      ACCEPT_TOKEN(sym_identifier);
      if (lookahead == 'w') ADVANCE(46);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 69:
      ACCEPT_TOKEN(sym_identifier);
      if (lookahead == 'x') ADVANCE(66);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 70:
      ACCEPT_TOKEN(sym_identifier);
      if (lookahead == '\t' ||
          lookahead == '\r' ||
          lookahead == ' ' ||
          lookahead == '"') ADVANCE(74);
      if (lookahead != 0 &&
          lookahead != '\n') ADVANCE(70);
      END_STATE();
    case 71:
      ACCEPT_TOKEN(sym_identifier);
      if (('0' <= lookahead && lookahead <= '9')) ADVANCE(71);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 72:
      ACCEPT_TOKEN(sym_identifier);
      if (lookahead != 0 &&
          lookahead != '\t' &&
          lookahead != '\n' &&
          lookahead != '\r' &&
          lookahead != ' ' &&
          lookahead != '"') ADVANCE(72);
      END_STATE();
    case 73:
      ACCEPT_TOKEN(sym_string);
      END_STATE();
    case 74:
      ACCEPT_TOKEN(sym_comment);
      if (lookahead != 0 &&
          lookahead != '\n') ADVANCE(74);
      END_STATE();
    default:
      return false;
  }
}

static const TSLexMode ts_lex_modes[STATE_COUNT] = {
  [0] = {.lex_state = 0},
  [1] = {.lex_state = 29},
  [2] = {.lex_state = 1},
  [3] = {.lex_state = 29},
  [4] = {.lex_state = 29},
  [5] = {.lex_state = 29},
  [6] = {.lex_state = 29},
  [7] = {.lex_state = 1},
  [8] = {.lex_state = 1},
  [9] = {.lex_state = 28},
  [10] = {.lex_state = 29},
  [11] = {.lex_state = 29},
  [12] = {.lex_state = 28},
  [13] = {.lex_state = 29},
  [14] = {.lex_state = 2},
  [15] = {.lex_state = 2},
  [16] = {.lex_state = 28},
  [17] = {.lex_state = 1},
  [18] = {.lex_state = 2},
  [19] = {.lex_state = 29},
  [20] = {.lex_state = 1},
  [21] = {.lex_state = 28},
  [22] = {.lex_state = 29},
  [23] = {.lex_state = 1},
  [24] = {.lex_state = 1},
  [25] = {.lex_state = 28},
  [26] = {.lex_state = 28},
  [27] = {.lex_state = 1},
  [28] = {.lex_state = 29},
  [29] = {.lex_state = 28},
  [30] = {.lex_state = 28},
  [31] = {.lex_state = 1},
  [32] = {.lex_state = 29},
  [33] = {.lex_state = 2},
  [34] = {.lex_state = 29},
  [35] = {.lex_state = 2},
  [36] = {.lex_state = 2},
  [37] = {.lex_state = 2},
  [38] = {.lex_state = 2},
  [39] = {.lex_state = 3},
  [40] = {.lex_state = 3},
  [41] = {.lex_state = 3},
  [42] = {.lex_state = 29},
  [43] = {.lex_state = 3},
  [44] = {.lex_state = 3},
  [45] = {.lex_state = 3},
  [46] = {.lex_state = 3},
  [47] = {.lex_state = 29},
  [48] = {.lex_state = 3},
  [49] = {.lex_state = 3},
  [50] = {.lex_state = 3},
  [51] = {.lex_state = 3},
  [52] = {.lex_state = 3},
  [53] = {.lex_state = 3},
  [54] = {.lex_state = 3},
  [55] = {.lex_state = 3},
};

static const uint16_t ts_parse_table[LARGE_STATE_COUNT][SYMBOL_COUNT] = {
  [0] = {
    [ts_builtin_sym_end] = ACTIONS(1),
    [anon_sym_config] = ACTIONS(1),
    [anon_sym_end] = ACTIONS(1),
    [anon_sym_edit] = ACTIONS(1),
    [anon_sym_next] = ACTIONS(1),
    [anon_sym_set] = ACTIONS(1),
    [anon_sym_unset] = ACTIONS(1),
    [anon_sym_get] = ACTIONS(1),
    [anon_sym_show] = ACTIONS(1),
    [sym_identifier] = ACTIONS(1),
    [sym_string] = ACTIONS(1),
    [sym_multiline_string] = ACTIONS(1),
    [sym_number] = ACTIONS(1),
    [sym_comment] = ACTIONS(3),
  },
  [1] = {
    [sym_source_file] = STATE(47),
    [sym__statement] = STATE(3),
    [sym_config_block] = STATE(3),
    [sym_edit_block] = STATE(3),
    [sym_set_cmd] = STATE(3),
    [sym_unset_cmd] = STATE(3),
    [sym_get_cmd] = STATE(3),
    [sym_show_cmd] = STATE(3),
    [aux_sym_source_file_repeat1] = STATE(3),
    [ts_builtin_sym_end] = ACTIONS(5),
    [anon_sym_config] = ACTIONS(7),
    [anon_sym_edit] = ACTIONS(9),
    [anon_sym_set] = ACTIONS(11),
    [anon_sym_unset] = ACTIONS(13),
    [anon_sym_get] = ACTIONS(15),
    [anon_sym_show] = ACTIONS(17),
    [sym_comment] = ACTIONS(19),
  },
  [2] = {
    [sym_config_block] = STATE(5),
    [sym__config_body_element] = STATE(5),
    [sym_edit_block] = STATE(5),
    [sym_set_cmd] = STATE(5),
    [sym_unset_cmd] = STATE(5),
    [sym_get_cmd] = STATE(5),
    [sym_show_cmd] = STATE(5),
    [aux_sym_config_block_repeat1] = STATE(23),
    [aux_sym_config_block_repeat2] = STATE(5),
    [anon_sym_config] = ACTIONS(21),
    [anon_sym_end] = ACTIONS(23),
    [anon_sym_edit] = ACTIONS(25),
    [anon_sym_set] = ACTIONS(27),
    [anon_sym_unset] = ACTIONS(29),
    [anon_sym_get] = ACTIONS(31),
    [anon_sym_show] = ACTIONS(33),
    [sym_identifier] = ACTIONS(35),
    [sym_comment] = ACTIONS(3),
  },
  [3] = {
    [sym__statement] = STATE(6),
    [sym_config_block] = STATE(6),
    [sym_edit_block] = STATE(6),
    [sym_set_cmd] = STATE(6),
    [sym_unset_cmd] = STATE(6),
    [sym_get_cmd] = STATE(6),
    [sym_show_cmd] = STATE(6),
    [aux_sym_source_file_repeat1] = STATE(6),
    [ts_builtin_sym_end] = ACTIONS(37),
    [anon_sym_config] = ACTIONS(7),
    [anon_sym_edit] = ACTIONS(9),
    [anon_sym_set] = ACTIONS(11),
    [anon_sym_unset] = ACTIONS(13),
    [anon_sym_get] = ACTIONS(15),
    [anon_sym_show] = ACTIONS(17),
    [sym_comment] = ACTIONS(19),
  },
  [4] = {
    [sym_config_block] = STATE(4),
    [sym__config_body_element] = STATE(4),
    [sym_edit_block] = STATE(4),
    [sym_set_cmd] = STATE(4),
    [sym_unset_cmd] = STATE(4),
    [sym_get_cmd] = STATE(4),
    [sym_show_cmd] = STATE(4),
    [aux_sym_config_block_repeat2] = STATE(4),
    [anon_sym_config] = ACTIONS(39),
    [anon_sym_end] = ACTIONS(42),
    [anon_sym_edit] = ACTIONS(44),
    [anon_sym_set] = ACTIONS(47),
    [anon_sym_unset] = ACTIONS(50),
    [anon_sym_get] = ACTIONS(53),
    [anon_sym_show] = ACTIONS(56),
    [sym_comment] = ACTIONS(19),
  },
  [5] = {
    [sym_config_block] = STATE(4),
    [sym__config_body_element] = STATE(4),
    [sym_edit_block] = STATE(4),
    [sym_set_cmd] = STATE(4),
    [sym_unset_cmd] = STATE(4),
    [sym_get_cmd] = STATE(4),
    [sym_show_cmd] = STATE(4),
    [aux_sym_config_block_repeat2] = STATE(4),
    [anon_sym_config] = ACTIONS(7),
    [anon_sym_end] = ACTIONS(59),
    [anon_sym_edit] = ACTIONS(9),
    [anon_sym_set] = ACTIONS(61),
    [anon_sym_unset] = ACTIONS(13),
    [anon_sym_get] = ACTIONS(63),
    [anon_sym_show] = ACTIONS(65),
    [sym_comment] = ACTIONS(19),
  },
  [6] = {
    [sym__statement] = STATE(6),
    [sym_config_block] = STATE(6),
    [sym_edit_block] = STATE(6),
    [sym_set_cmd] = STATE(6),
    [sym_unset_cmd] = STATE(6),
    [sym_get_cmd] = STATE(6),
    [sym_show_cmd] = STATE(6),
    [aux_sym_source_file_repeat1] = STATE(6),
    [ts_builtin_sym_end] = ACTIONS(67),
    [anon_sym_config] = ACTIONS(69),
    [anon_sym_edit] = ACTIONS(72),
    [anon_sym_set] = ACTIONS(75),
    [anon_sym_unset] = ACTIONS(78),
    [anon_sym_get] = ACTIONS(81),
    [anon_sym_show] = ACTIONS(84),
    [sym_comment] = ACTIONS(19),
  },
};

static const uint16_t ts_small_parse_table[] = {
  [0] = 5,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(92), 1,
      sym_string,
    STATE(7), 2,
      sym_value_part,
      aux_sym_set_cmd_repeat1,
    ACTIONS(89), 3,
      sym_identifier,
      sym_multiline_string,
      sym_number,
    ACTIONS(87), 7,
      anon_sym_config,
      anon_sym_end,
      anon_sym_edit,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
  [25] = 5,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(99), 1,
      sym_string,
    STATE(7), 2,
      sym_value_part,
      aux_sym_set_cmd_repeat1,
    ACTIONS(97), 3,
      sym_identifier,
      sym_multiline_string,
      sym_number,
    ACTIONS(95), 7,
      anon_sym_config,
      anon_sym_end,
      anon_sym_edit,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
  [50] = 6,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(101), 1,
      ts_builtin_sym_end,
    ACTIONS(106), 1,
      sym_string,
    STATE(9), 2,
      sym_value_part,
      aux_sym_set_cmd_repeat1,
    ACTIONS(103), 3,
      sym_identifier,
      sym_multiline_string,
      sym_number,
    ACTIONS(87), 6,
      anon_sym_config,
      anon_sym_edit,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
  [77] = 8,
    ACTIONS(19), 1,
      sym_comment,
    ACTIONS(109), 1,
      anon_sym_config,
    ACTIONS(112), 1,
      anon_sym_next,
    ACTIONS(114), 1,
      anon_sym_set,
    ACTIONS(117), 1,
      anon_sym_unset,
    ACTIONS(120), 1,
      anon_sym_get,
    ACTIONS(123), 1,
      anon_sym_show,
    STATE(10), 7,
      sym_config_block,
      sym__edit_body_element,
      sym_set_cmd,
      sym_unset_cmd,
      sym_get_cmd,
      sym_show_cmd,
      aux_sym_edit_block_repeat1,
  [108] = 8,
    ACTIONS(7), 1,
      anon_sym_config,
    ACTIONS(13), 1,
      anon_sym_unset,
    ACTIONS(19), 1,
      sym_comment,
    ACTIONS(126), 1,
      anon_sym_next,
    ACTIONS(128), 1,
      anon_sym_set,
    ACTIONS(130), 1,
      anon_sym_get,
    ACTIONS(132), 1,
      anon_sym_show,
    STATE(13), 7,
      sym_config_block,
      sym__edit_body_element,
      sym_set_cmd,
      sym_unset_cmd,
      sym_get_cmd,
      sym_show_cmd,
      aux_sym_edit_block_repeat1,
  [139] = 6,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(134), 1,
      ts_builtin_sym_end,
    ACTIONS(138), 1,
      sym_string,
    STATE(9), 2,
      sym_value_part,
      aux_sym_set_cmd_repeat1,
    ACTIONS(136), 3,
      sym_identifier,
      sym_multiline_string,
      sym_number,
    ACTIONS(95), 6,
      anon_sym_config,
      anon_sym_edit,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
  [166] = 8,
    ACTIONS(7), 1,
      anon_sym_config,
    ACTIONS(13), 1,
      anon_sym_unset,
    ACTIONS(19), 1,
      sym_comment,
    ACTIONS(128), 1,
      anon_sym_set,
    ACTIONS(130), 1,
      anon_sym_get,
    ACTIONS(132), 1,
      anon_sym_show,
    ACTIONS(140), 1,
      anon_sym_next,
    STATE(10), 7,
      sym_config_block,
      sym__edit_body_element,
      sym_set_cmd,
      sym_unset_cmd,
      sym_get_cmd,
      sym_show_cmd,
      aux_sym_edit_block_repeat1,
  [197] = 5,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(145), 1,
      sym_string,
    STATE(14), 2,
      sym_value_part,
      aux_sym_set_cmd_repeat1,
    ACTIONS(142), 3,
      sym_identifier,
      sym_multiline_string,
      sym_number,
    ACTIONS(87), 6,
      anon_sym_config,
      anon_sym_next,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
  [221] = 5,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(150), 1,
      sym_string,
    STATE(14), 2,
      sym_value_part,
      aux_sym_set_cmd_repeat1,
    ACTIONS(148), 3,
      sym_identifier,
      sym_multiline_string,
      sym_number,
    ACTIONS(95), 6,
      anon_sym_config,
      anon_sym_next,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
  [245] = 3,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(152), 2,
      ts_builtin_sym_end,
      sym_string,
    ACTIONS(154), 9,
      anon_sym_config,
      anon_sym_edit,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
      sym_identifier,
      sym_multiline_string,
      sym_number,
  [264] = 3,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(152), 1,
      sym_string,
    ACTIONS(154), 10,
      anon_sym_config,
      anon_sym_end,
      anon_sym_edit,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
      sym_identifier,
      sym_multiline_string,
      sym_number,
  [283] = 3,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(152), 1,
      sym_string,
    ACTIONS(154), 9,
      anon_sym_config,
      anon_sym_next,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
      sym_identifier,
      sym_multiline_string,
      sym_number,
  [301] = 2,
    ACTIONS(19), 1,
      sym_comment,
    ACTIONS(156), 9,
      ts_builtin_sym_end,
      anon_sym_config,
      anon_sym_end,
      anon_sym_edit,
      anon_sym_next,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
  [316] = 4,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(160), 1,
      sym_identifier,
    STATE(24), 1,
      aux_sym_config_block_repeat1,
    ACTIONS(158), 7,
      anon_sym_config,
      anon_sym_end,
      anon_sym_edit,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
  [335] = 5,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(162), 1,
      ts_builtin_sym_end,
    ACTIONS(164), 1,
      sym_identifier,
    STATE(26), 1,
      aux_sym_config_block_repeat1,
    ACTIONS(158), 6,
      anon_sym_config,
      anon_sym_edit,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
  [356] = 2,
    ACTIONS(19), 1,
      sym_comment,
    ACTIONS(166), 9,
      ts_builtin_sym_end,
      anon_sym_config,
      anon_sym_end,
      anon_sym_edit,
      anon_sym_next,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
  [371] = 4,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(170), 1,
      sym_identifier,
    STATE(23), 1,
      aux_sym_config_block_repeat1,
    ACTIONS(168), 7,
      anon_sym_config,
      anon_sym_end,
      anon_sym_edit,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
  [390] = 4,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(35), 1,
      sym_identifier,
    STATE(23), 1,
      aux_sym_config_block_repeat1,
    ACTIONS(173), 7,
      anon_sym_config,
      anon_sym_end,
      anon_sym_edit,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
  [409] = 5,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(175), 1,
      ts_builtin_sym_end,
    ACTIONS(179), 1,
      sym_identifier,
    STATE(30), 1,
      aux_sym_config_block_repeat1,
    ACTIONS(177), 6,
      anon_sym_config,
      anon_sym_edit,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
  [430] = 5,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(179), 1,
      sym_identifier,
    ACTIONS(181), 1,
      ts_builtin_sym_end,
    STATE(30), 1,
      aux_sym_config_block_repeat1,
    ACTIONS(173), 6,
      anon_sym_config,
      anon_sym_edit,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
  [451] = 4,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(35), 1,
      sym_identifier,
    STATE(23), 1,
      aux_sym_config_block_repeat1,
    ACTIONS(177), 7,
      anon_sym_config,
      anon_sym_end,
      anon_sym_edit,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
  [470] = 2,
    ACTIONS(19), 1,
      sym_comment,
    ACTIONS(183), 9,
      ts_builtin_sym_end,
      anon_sym_config,
      anon_sym_end,
      anon_sym_edit,
      anon_sym_next,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
  [485] = 5,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(185), 1,
      ts_builtin_sym_end,
    ACTIONS(189), 1,
      sym_identifier,
    STATE(25), 1,
      aux_sym_config_block_repeat1,
    ACTIONS(187), 6,
      anon_sym_config,
      anon_sym_edit,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
  [506] = 5,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(191), 1,
      ts_builtin_sym_end,
    ACTIONS(193), 1,
      sym_identifier,
    STATE(30), 1,
      aux_sym_config_block_repeat1,
    ACTIONS(168), 6,
      anon_sym_config,
      anon_sym_edit,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
  [527] = 4,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(196), 1,
      sym_identifier,
    STATE(27), 1,
      aux_sym_config_block_repeat1,
    ACTIONS(187), 7,
      anon_sym_config,
      anon_sym_end,
      anon_sym_edit,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
  [546] = 2,
    ACTIONS(19), 1,
      sym_comment,
    ACTIONS(198), 8,
      ts_builtin_sym_end,
      anon_sym_config,
      anon_sym_end,
      anon_sym_edit,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
  [560] = 4,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(200), 1,
      sym_identifier,
    STATE(37), 1,
      aux_sym_config_block_repeat1,
    ACTIONS(173), 6,
      anon_sym_config,
      anon_sym_next,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
  [578] = 2,
    ACTIONS(19), 1,
      sym_comment,
    ACTIONS(202), 8,
      ts_builtin_sym_end,
      anon_sym_config,
      anon_sym_end,
      anon_sym_edit,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
  [592] = 4,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(204), 1,
      sym_identifier,
    STATE(38), 1,
      aux_sym_config_block_repeat1,
    ACTIONS(187), 6,
      anon_sym_config,
      anon_sym_next,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
  [610] = 4,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(206), 1,
      sym_identifier,
    STATE(33), 1,
      aux_sym_config_block_repeat1,
    ACTIONS(158), 6,
      anon_sym_config,
      anon_sym_next,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
  [628] = 4,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(208), 1,
      sym_identifier,
    STATE(37), 1,
      aux_sym_config_block_repeat1,
    ACTIONS(168), 6,
      anon_sym_config,
      anon_sym_next,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
  [646] = 4,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(200), 1,
      sym_identifier,
    STATE(37), 1,
      aux_sym_config_block_repeat1,
    ACTIONS(177), 6,
      anon_sym_config,
      anon_sym_next,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
  [664] = 4,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(150), 1,
      sym_string,
    STATE(15), 2,
      sym_value_part,
      aux_sym_set_cmd_repeat1,
    ACTIONS(148), 3,
      sym_identifier,
      sym_multiline_string,
      sym_number,
  [680] = 4,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(99), 1,
      sym_string,
    STATE(8), 2,
      sym_value_part,
      aux_sym_set_cmd_repeat1,
    ACTIONS(97), 3,
      sym_identifier,
      sym_multiline_string,
      sym_number,
  [696] = 4,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(138), 1,
      sym_string,
    STATE(12), 2,
      sym_value_part,
      aux_sym_set_cmd_repeat1,
    ACTIONS(136), 3,
      sym_identifier,
      sym_multiline_string,
      sym_number,
  [712] = 2,
    ACTIONS(19), 1,
      sym_comment,
    ACTIONS(211), 6,
      anon_sym_config,
      anon_sym_next,
      anon_sym_set,
      anon_sym_unset,
      anon_sym_get,
      anon_sym_show,
  [724] = 4,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(215), 1,
      sym_string,
    STATE(11), 1,
      sym_id,
    ACTIONS(213), 2,
      sym_identifier,
      sym_number,
  [738] = 3,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(217), 1,
      sym_identifier,
    STATE(2), 1,
      aux_sym_config_block_repeat1,
  [748] = 2,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(219), 1,
      sym_identifier,
  [755] = 2,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(221), 1,
      sym_identifier,
  [762] = 2,
    ACTIONS(19), 1,
      sym_comment,
    ACTIONS(223), 1,
      ts_builtin_sym_end,
  [769] = 2,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(225), 1,
      sym_identifier,
  [776] = 2,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(227), 1,
      sym_identifier,
  [783] = 2,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(229), 1,
      sym_identifier,
  [790] = 2,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(231), 1,
      sym_identifier,
  [797] = 2,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(233), 1,
      sym_identifier,
  [804] = 2,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(235), 1,
      sym_identifier,
  [811] = 2,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(237), 1,
      sym_identifier,
  [818] = 2,
    ACTIONS(3), 1,
      sym_comment,
    ACTIONS(239), 1,
      sym_identifier,
};

static const uint32_t ts_small_parse_table_map[] = {
  [SMALL_STATE(7)] = 0,
  [SMALL_STATE(8)] = 25,
  [SMALL_STATE(9)] = 50,
  [SMALL_STATE(10)] = 77,
  [SMALL_STATE(11)] = 108,
  [SMALL_STATE(12)] = 139,
  [SMALL_STATE(13)] = 166,
  [SMALL_STATE(14)] = 197,
  [SMALL_STATE(15)] = 221,
  [SMALL_STATE(16)] = 245,
  [SMALL_STATE(17)] = 264,
  [SMALL_STATE(18)] = 283,
  [SMALL_STATE(19)] = 301,
  [SMALL_STATE(20)] = 316,
  [SMALL_STATE(21)] = 335,
  [SMALL_STATE(22)] = 356,
  [SMALL_STATE(23)] = 371,
  [SMALL_STATE(24)] = 390,
  [SMALL_STATE(25)] = 409,
  [SMALL_STATE(26)] = 430,
  [SMALL_STATE(27)] = 451,
  [SMALL_STATE(28)] = 470,
  [SMALL_STATE(29)] = 485,
  [SMALL_STATE(30)] = 506,
  [SMALL_STATE(31)] = 527,
  [SMALL_STATE(32)] = 546,
  [SMALL_STATE(33)] = 560,
  [SMALL_STATE(34)] = 578,
  [SMALL_STATE(35)] = 592,
  [SMALL_STATE(36)] = 610,
  [SMALL_STATE(37)] = 628,
  [SMALL_STATE(38)] = 646,
  [SMALL_STATE(39)] = 664,
  [SMALL_STATE(40)] = 680,
  [SMALL_STATE(41)] = 696,
  [SMALL_STATE(42)] = 712,
  [SMALL_STATE(43)] = 724,
  [SMALL_STATE(44)] = 738,
  [SMALL_STATE(45)] = 748,
  [SMALL_STATE(46)] = 755,
  [SMALL_STATE(47)] = 762,
  [SMALL_STATE(48)] = 769,
  [SMALL_STATE(49)] = 776,
  [SMALL_STATE(50)] = 783,
  [SMALL_STATE(51)] = 790,
  [SMALL_STATE(52)] = 797,
  [SMALL_STATE(53)] = 804,
  [SMALL_STATE(54)] = 811,
  [SMALL_STATE(55)] = 818,
};

static const TSParseActionEntry ts_parse_actions[] = {
  [0] = {.entry = {.count = 0, .reusable = false}},
  [1] = {.entry = {.count = 1, .reusable = false}}, RECOVER(),
  [3] = {.entry = {.count = 1, .reusable = false}}, SHIFT_EXTRA(),
  [5] = {.entry = {.count = 1, .reusable = true}}, REDUCE(sym_source_file, 0),
  [7] = {.entry = {.count = 1, .reusable = true}}, SHIFT(44),
  [9] = {.entry = {.count = 1, .reusable = true}}, SHIFT(43),
  [11] = {.entry = {.count = 1, .reusable = true}}, SHIFT(46),
  [13] = {.entry = {.count = 1, .reusable = true}}, SHIFT(45),
  [15] = {.entry = {.count = 1, .reusable = true}}, SHIFT(50),
  [17] = {.entry = {.count = 1, .reusable = true}}, SHIFT(53),
  [19] = {.entry = {.count = 1, .reusable = true}}, SHIFT_EXTRA(),
  [21] = {.entry = {.count = 1, .reusable = false}}, SHIFT(44),
  [23] = {.entry = {.count = 1, .reusable = false}}, SHIFT(22),
  [25] = {.entry = {.count = 1, .reusable = false}}, SHIFT(43),
  [27] = {.entry = {.count = 1, .reusable = false}}, SHIFT(54),
  [29] = {.entry = {.count = 1, .reusable = false}}, SHIFT(45),
  [31] = {.entry = {.count = 1, .reusable = false}}, SHIFT(48),
  [33] = {.entry = {.count = 1, .reusable = false}}, SHIFT(49),
  [35] = {.entry = {.count = 1, .reusable = false}}, SHIFT(23),
  [37] = {.entry = {.count = 1, .reusable = true}}, REDUCE(sym_source_file, 1),
  [39] = {.entry = {.count = 2, .reusable = true}}, REDUCE(aux_sym_config_block_repeat2, 2), SHIFT_REPEAT(44),
  [42] = {.entry = {.count = 1, .reusable = true}}, REDUCE(aux_sym_config_block_repeat2, 2),
  [44] = {.entry = {.count = 2, .reusable = true}}, REDUCE(aux_sym_config_block_repeat2, 2), SHIFT_REPEAT(43),
  [47] = {.entry = {.count = 2, .reusable = true}}, REDUCE(aux_sym_config_block_repeat2, 2), SHIFT_REPEAT(54),
  [50] = {.entry = {.count = 2, .reusable = true}}, REDUCE(aux_sym_config_block_repeat2, 2), SHIFT_REPEAT(45),
  [53] = {.entry = {.count = 2, .reusable = true}}, REDUCE(aux_sym_config_block_repeat2, 2), SHIFT_REPEAT(48),
  [56] = {.entry = {.count = 2, .reusable = true}}, REDUCE(aux_sym_config_block_repeat2, 2), SHIFT_REPEAT(49),
  [59] = {.entry = {.count = 1, .reusable = true}}, SHIFT(19),
  [61] = {.entry = {.count = 1, .reusable = true}}, SHIFT(54),
  [63] = {.entry = {.count = 1, .reusable = true}}, SHIFT(48),
  [65] = {.entry = {.count = 1, .reusable = true}}, SHIFT(49),
  [67] = {.entry = {.count = 1, .reusable = true}}, REDUCE(aux_sym_source_file_repeat1, 2),
  [69] = {.entry = {.count = 2, .reusable = true}}, REDUCE(aux_sym_source_file_repeat1, 2), SHIFT_REPEAT(44),
  [72] = {.entry = {.count = 2, .reusable = true}}, REDUCE(aux_sym_source_file_repeat1, 2), SHIFT_REPEAT(43),
  [75] = {.entry = {.count = 2, .reusable = true}}, REDUCE(aux_sym_source_file_repeat1, 2), SHIFT_REPEAT(46),
  [78] = {.entry = {.count = 2, .reusable = true}}, REDUCE(aux_sym_source_file_repeat1, 2), SHIFT_REPEAT(45),
  [81] = {.entry = {.count = 2, .reusable = true}}, REDUCE(aux_sym_source_file_repeat1, 2), SHIFT_REPEAT(50),
  [84] = {.entry = {.count = 2, .reusable = true}}, REDUCE(aux_sym_source_file_repeat1, 2), SHIFT_REPEAT(53),
  [87] = {.entry = {.count = 1, .reusable = false}}, REDUCE(aux_sym_set_cmd_repeat1, 2),
  [89] = {.entry = {.count = 2, .reusable = false}}, REDUCE(aux_sym_set_cmd_repeat1, 2), SHIFT_REPEAT(17),
  [92] = {.entry = {.count = 2, .reusable = true}}, REDUCE(aux_sym_set_cmd_repeat1, 2), SHIFT_REPEAT(17),
  [95] = {.entry = {.count = 1, .reusable = false}}, REDUCE(sym_set_cmd, 3),
  [97] = {.entry = {.count = 1, .reusable = false}}, SHIFT(17),
  [99] = {.entry = {.count = 1, .reusable = true}}, SHIFT(17),
  [101] = {.entry = {.count = 1, .reusable = true}}, REDUCE(aux_sym_set_cmd_repeat1, 2),
  [103] = {.entry = {.count = 2, .reusable = false}}, REDUCE(aux_sym_set_cmd_repeat1, 2), SHIFT_REPEAT(16),
  [106] = {.entry = {.count = 2, .reusable = true}}, REDUCE(aux_sym_set_cmd_repeat1, 2), SHIFT_REPEAT(16),
  [109] = {.entry = {.count = 2, .reusable = true}}, REDUCE(aux_sym_edit_block_repeat1, 2), SHIFT_REPEAT(44),
  [112] = {.entry = {.count = 1, .reusable = true}}, REDUCE(aux_sym_edit_block_repeat1, 2),
  [114] = {.entry = {.count = 2, .reusable = true}}, REDUCE(aux_sym_edit_block_repeat1, 2), SHIFT_REPEAT(55),
  [117] = {.entry = {.count = 2, .reusable = true}}, REDUCE(aux_sym_edit_block_repeat1, 2), SHIFT_REPEAT(45),
  [120] = {.entry = {.count = 2, .reusable = true}}, REDUCE(aux_sym_edit_block_repeat1, 2), SHIFT_REPEAT(51),
  [123] = {.entry = {.count = 2, .reusable = true}}, REDUCE(aux_sym_edit_block_repeat1, 2), SHIFT_REPEAT(52),
  [126] = {.entry = {.count = 1, .reusable = true}}, SHIFT(34),
  [128] = {.entry = {.count = 1, .reusable = true}}, SHIFT(55),
  [130] = {.entry = {.count = 1, .reusable = true}}, SHIFT(51),
  [132] = {.entry = {.count = 1, .reusable = true}}, SHIFT(52),
  [134] = {.entry = {.count = 1, .reusable = true}}, REDUCE(sym_set_cmd, 3),
  [136] = {.entry = {.count = 1, .reusable = false}}, SHIFT(16),
  [138] = {.entry = {.count = 1, .reusable = true}}, SHIFT(16),
  [140] = {.entry = {.count = 1, .reusable = true}}, SHIFT(32),
  [142] = {.entry = {.count = 2, .reusable = false}}, REDUCE(aux_sym_set_cmd_repeat1, 2), SHIFT_REPEAT(18),
  [145] = {.entry = {.count = 2, .reusable = true}}, REDUCE(aux_sym_set_cmd_repeat1, 2), SHIFT_REPEAT(18),
  [148] = {.entry = {.count = 1, .reusable = false}}, SHIFT(18),
  [150] = {.entry = {.count = 1, .reusable = true}}, SHIFT(18),
  [152] = {.entry = {.count = 1, .reusable = true}}, REDUCE(sym_value_part, 1),
  [154] = {.entry = {.count = 1, .reusable = false}}, REDUCE(sym_value_part, 1),
  [156] = {.entry = {.count = 1, .reusable = true}}, REDUCE(sym_config_block, 4),
  [158] = {.entry = {.count = 1, .reusable = false}}, REDUCE(sym_show_cmd, 2),
  [160] = {.entry = {.count = 1, .reusable = false}}, SHIFT(24),
  [162] = {.entry = {.count = 1, .reusable = true}}, REDUCE(sym_show_cmd, 2),
  [164] = {.entry = {.count = 1, .reusable = false}}, SHIFT(26),
  [166] = {.entry = {.count = 1, .reusable = true}}, REDUCE(sym_config_block, 3),
  [168] = {.entry = {.count = 1, .reusable = false}}, REDUCE(aux_sym_config_block_repeat1, 2),
  [170] = {.entry = {.count = 2, .reusable = false}}, REDUCE(aux_sym_config_block_repeat1, 2), SHIFT_REPEAT(23),
  [173] = {.entry = {.count = 1, .reusable = false}}, REDUCE(sym_show_cmd, 3),
  [175] = {.entry = {.count = 1, .reusable = true}}, REDUCE(sym_get_cmd, 3),
  [177] = {.entry = {.count = 1, .reusable = false}}, REDUCE(sym_get_cmd, 3),
  [179] = {.entry = {.count = 1, .reusable = false}}, SHIFT(30),
  [181] = {.entry = {.count = 1, .reusable = true}}, REDUCE(sym_show_cmd, 3),
  [183] = {.entry = {.count = 1, .reusable = true}}, REDUCE(sym_unset_cmd, 2),
  [185] = {.entry = {.count = 1, .reusable = true}}, REDUCE(sym_get_cmd, 2),
  [187] = {.entry = {.count = 1, .reusable = false}}, REDUCE(sym_get_cmd, 2),
  [189] = {.entry = {.count = 1, .reusable = false}}, SHIFT(25),
  [191] = {.entry = {.count = 1, .reusable = true}}, REDUCE(aux_sym_config_block_repeat1, 2),
  [193] = {.entry = {.count = 2, .reusable = false}}, REDUCE(aux_sym_config_block_repeat1, 2), SHIFT_REPEAT(30),
  [196] = {.entry = {.count = 1, .reusable = false}}, SHIFT(27),
  [198] = {.entry = {.count = 1, .reusable = true}}, REDUCE(sym_edit_block, 4),
  [200] = {.entry = {.count = 1, .reusable = false}}, SHIFT(37),
  [202] = {.entry = {.count = 1, .reusable = true}}, REDUCE(sym_edit_block, 3),
  [204] = {.entry = {.count = 1, .reusable = false}}, SHIFT(38),
  [206] = {.entry = {.count = 1, .reusable = false}}, SHIFT(33),
  [208] = {.entry = {.count = 2, .reusable = false}}, REDUCE(aux_sym_config_block_repeat1, 2), SHIFT_REPEAT(37),
  [211] = {.entry = {.count = 1, .reusable = true}}, REDUCE(sym_id, 1),
  [213] = {.entry = {.count = 1, .reusable = false}}, SHIFT(42),
  [215] = {.entry = {.count = 1, .reusable = true}}, SHIFT(42),
  [217] = {.entry = {.count = 1, .reusable = false}}, SHIFT(2),
  [219] = {.entry = {.count = 1, .reusable = false}}, SHIFT(28),
  [221] = {.entry = {.count = 1, .reusable = false}}, SHIFT(41),
  [223] = {.entry = {.count = 1, .reusable = true}},  ACCEPT_INPUT(),
  [225] = {.entry = {.count = 1, .reusable = false}}, SHIFT(31),
  [227] = {.entry = {.count = 1, .reusable = false}}, SHIFT(20),
  [229] = {.entry = {.count = 1, .reusable = false}}, SHIFT(29),
  [231] = {.entry = {.count = 1, .reusable = false}}, SHIFT(35),
  [233] = {.entry = {.count = 1, .reusable = false}}, SHIFT(36),
  [235] = {.entry = {.count = 1, .reusable = false}}, SHIFT(21),
  [237] = {.entry = {.count = 1, .reusable = false}}, SHIFT(40),
  [239] = {.entry = {.count = 1, .reusable = false}}, SHIFT(39),
};

#ifdef __cplusplus
extern "C" {
#endif
#ifdef _WIN32
#define extern __declspec(dllexport)
#endif

extern const TSLanguage *tree_sitter_fortios(void) {
  static const TSLanguage language = {
    .version = LANGUAGE_VERSION,
    .symbol_count = SYMBOL_COUNT,
    .alias_count = ALIAS_COUNT,
    .token_count = TOKEN_COUNT,
    .external_token_count = EXTERNAL_TOKEN_COUNT,
    .state_count = STATE_COUNT,
    .large_state_count = LARGE_STATE_COUNT,
    .production_id_count = PRODUCTION_ID_COUNT,
    .field_count = FIELD_COUNT,
    .max_alias_sequence_length = MAX_ALIAS_SEQUENCE_LENGTH,
    .parse_table = &ts_parse_table[0][0],
    .small_parse_table = ts_small_parse_table,
    .small_parse_table_map = ts_small_parse_table_map,
    .parse_actions = ts_parse_actions,
    .symbol_names = ts_symbol_names,
    .symbol_metadata = ts_symbol_metadata,
    .public_symbol_map = ts_symbol_map,
    .alias_map = ts_non_terminal_alias_map,
    .alias_sequences = &ts_alias_sequences[0][0],
    .lex_modes = ts_lex_modes,
    .lex_fn = ts_lex,
    .primary_state_ids = ts_primary_state_ids,
  };
  return &language;
}
#ifdef __cplusplus
}
#endif

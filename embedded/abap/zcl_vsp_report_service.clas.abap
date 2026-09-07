CLASS zcl_vsp_report_service DEFINITION
  PUBLIC
  FINAL
  CREATE PUBLIC.

  PUBLIC SECTION.
    INTERFACES zif_vsp_service.

  PRIVATE SECTION.
    METHODS handle_run_report
      IMPORTING is_message         TYPE zif_vsp_service=>ty_message
      RETURNING VALUE(rs_response) TYPE zif_vsp_service=>ty_response.

    METHODS handle_get_job_status
      IMPORTING is_message         TYPE zif_vsp_service=>ty_message
      RETURNING VALUE(rs_response) TYPE zif_vsp_service=>ty_response.

    METHODS handle_get_spool_output
      IMPORTING is_message         TYPE zif_vsp_service=>ty_message
      RETURNING VALUE(rs_response) TYPE zif_vsp_service=>ty_response.

    METHODS handle_get_text_elements
      IMPORTING is_message         TYPE zif_vsp_service=>ty_message
      RETURNING VALUE(rs_response) TYPE zif_vsp_service=>ty_response.

    METHODS handle_set_text_elements
      IMPORTING is_message         TYPE zif_vsp_service=>ty_message
      RETURNING VALUE(rs_response) TYPE zif_vsp_service=>ty_response.

    METHODS handle_get_variants
      IMPORTING is_message         TYPE zif_vsp_service=>ty_message
      RETURNING VALUE(rs_response) TYPE zif_vsp_service=>ty_response.

    METHODS extract_param
      IMPORTING iv_params       TYPE string
                iv_name         TYPE string
      RETURNING VALUE(rv_value) TYPE string.

    METHODS extract_param_object
      IMPORTING iv_params      TYPE string
                iv_name        TYPE string
      RETURNING VALUE(rv_json) TYPE string.

    METHODS escape_json
      IMPORTING iv_string         TYPE string
      RETURNING VALUE(rv_escaped) TYPE string.

    METHODS build_error
      IMPORTING iv_id              TYPE string
                iv_code            TYPE string
                iv_message         TYPE string
      RETURNING VALUE(rs_response) TYPE zif_vsp_service=>ty_response.

ENDCLASS.


CLASS zcl_vsp_report_service IMPLEMENTATION.

  METHOD zif_vsp_service~get_domain.
    rv_domain = 'report'.
  ENDMETHOD.

  METHOD zif_vsp_service~handle_message.
    CASE is_message-action.
      WHEN 'runReport'.
        rs_response = handle_run_report( is_message ).
      WHEN 'getJobStatus'.
        rs_response = handle_get_job_status( is_message ).
      WHEN 'getSpoolOutput'.
        rs_response = handle_get_spool_output( is_message ).
      WHEN 'getTextElements'.
        rs_response = handle_get_text_elements( is_message ).
      WHEN 'setTextElements'.
        rs_response = handle_set_text_elements( is_message ).
      WHEN 'getVariants'.
        rs_response = handle_get_variants( is_message ).
      WHEN OTHERS.
        rs_response = build_error(
          iv_id      = is_message-id
          iv_code    = 'UNKNOWN_ACTION'
          iv_message = |Action '{ is_message-action }' not supported|
        ).
    ENDCASE.
  ENDMETHOD.

  METHOD zif_vsp_service~on_disconnect.
  ENDMETHOD.

  METHOD handle_run_report.
    " APC context forbids plain SUBMIT (RABAX: invalid statement in push channel).
    " Run the report as a background job instead: JOB_OPEN -> SUBMIT VIA JOB -> JOB_CLOSE.
    " The client polls getJobStatus and reads spool via getSpoolOutput.
    DATA: lt_rsparams TYPE TABLE OF rsparams,
          lv_report   TYPE progname,
          lv_variant  TYPE variant,
          lv_jobname  TYPE tbtcjob-jobname,
          lv_jobcount TYPE tbtcjob-jobcount.

    DATA(lv_report_str) = extract_param( iv_params = is_message-params iv_name = 'report' ).
    DATA(lv_variant_str) = extract_param( iv_params = is_message-params iv_name = 'variant' ).
    DATA(lv_params_json) = extract_param_object( iv_params = is_message-params iv_name = 'params' ).

    IF lv_report_str IS INITIAL.
      rs_response = build_error( iv_id = is_message-id iv_code = 'MISSING_PARAM' iv_message = 'Parameter report is required' ).
      RETURN.
    ENDIF.

    TRANSLATE lv_report_str TO UPPER CASE.
    lv_report = lv_report_str.
    IF lv_variant_str IS NOT INITIAL.
      TRANSLATE lv_variant_str TO UPPER CASE.
      lv_variant = lv_variant_str.
    ENDIF.

    SELECT SINGLE name FROM trdir INTO @DATA(lv_exists) WHERE name = @lv_report.
    IF sy-subrc <> 0.
      rs_response = build_error( iv_id = is_message-id iv_code = 'REPORT_NOT_FOUND' iv_message = |Report { lv_report } not found| ).
      RETURN.
    ENDIF.

    IF lv_params_json IS NOT INITIAL.
      DATA(lv_work) = lv_params_json.
      WHILE lv_work CS '"'.
        DATA lv_pname TYPE string.
        DATA lv_pval TYPE string.
        FIND REGEX '"([^"]+)"\s*:\s*"([^"]*)"' IN lv_work SUBMATCHES lv_pname lv_pval.
        IF sy-subrc = 0.
          TRANSLATE lv_pname TO UPPER CASE.
          DATA lv_selname TYPE rsscr_name.
          lv_selname = lv_pname.
          APPEND VALUE rsparams(
            selname = lv_selname
            kind    = 'P'
            sign    = 'I'
            option  = 'EQ'
            low     = lv_pval
          ) TO lt_rsparams.
          FIND FIRST OCCURRENCE OF |"{ lv_pname }"| IN lv_work MATCH OFFSET DATA(lv_off) MATCH LENGTH DATA(lv_len) IGNORING CASE.
          IF sy-subrc = 0 AND strlen( lv_work ) > lv_off + lv_len.
            lv_work = lv_work+lv_off.
            lv_work = lv_work+lv_len.
          ELSE.
            EXIT.
          ENDIF.
        ELSE.
          EXIT.
        ENDIF.
      ENDWHILE.
    ENDIF.

    lv_jobname = |ZVSP_{ lv_report }|.

    CALL FUNCTION 'JOB_OPEN'
      EXPORTING
        jobname          = lv_jobname
      IMPORTING
        jobcount         = lv_jobcount
      EXCEPTIONS
        cant_create_job  = 1
        invalid_job_data = 2
        jobname_missing  = 3
        OTHERS           = 4.
    IF sy-subrc <> 0.
      rs_response = build_error( iv_id = is_message-id iv_code = 'JOB_OPEN_ERROR' iv_message = |JOB_OPEN failed, subrc { sy-subrc }| ).
      RETURN.
    ENDIF.

    " Any form of SUBMIT (even VIA JOB) is a forbidden statement inside an
    " ABAP push channel session - the kernel raises RABAX. JOB_SUBMIT is a
    " plain function call and passes. Trade-off: free parameters are not
    " supported, selections must come from a variant.
    IF lt_rsparams IS NOT INITIAL AND lv_variant IS INITIAL.
      rs_response = build_error( iv_id = is_message-id iv_code = 'PARAMS_NOT_SUPPORTED' iv_message = 'Free parameters are not supported in APC context; create a variant and pass variant=...' ).
      RETURN.
    ENDIF.

    CALL FUNCTION 'JOB_SUBMIT'
      EXPORTING
        authcknam               = sy-uname
        jobname                 = lv_jobname
        jobcount                = lv_jobcount
        report                  = lv_report
        variant                 = lv_variant
      EXCEPTIONS
        bad_priparams           = 1
        bad_xpgflags            = 2
        invalid_jobdata         = 3
        jobname_missing         = 4
        job_notex               = 5
        job_submit_failed       = 6
        lock_failed             = 7
        program_missing         = 8
        prog_abap_and_extpg_set = 9
        OTHERS                  = 10.
    IF sy-subrc <> 0.
      rs_response = build_error( iv_id = is_message-id iv_code = 'JOB_SUBMIT_ERROR' iv_message = |JOB_SUBMIT failed, subrc { sy-subrc }| ).
      RETURN.
    ENDIF.

    " Step 2: export step 1's spool to INDX so getSpoolOutput can read it
    " from the APC session without forbidden statements.
    CALL FUNCTION 'JOB_SUBMIT'
      EXPORTING
        authcknam = sy-uname
        jobname   = lv_jobname
        jobcount  = lv_jobcount
        report    = 'ZVSP_SPOOL_XPRT'
      EXCEPTIONS
        OTHERS    = 1.
    IF sy-subrc <> 0.
      rs_response = build_error( iv_id = is_message-id iv_code = 'JOB_SUBMIT_ERROR' iv_message = |JOB_SUBMIT of spool export step failed, subrc { sy-subrc }| ).
      RETURN.
    ENDIF.

    CALL FUNCTION 'JOB_CLOSE'
      EXPORTING
        jobname              = lv_jobname
        jobcount             = lv_jobcount
        strtimmed            = 'X'
      EXCEPTIONS
        cant_start_immediate = 1
        invalid_startdate    = 2
        jobname_missing      = 3
        job_close_failed     = 4
        job_nosteps          = 5
        job_notex            = 6
        lock_failed          = 7
        invalid_target       = 8
        OTHERS               = 9.
    IF sy-subrc <> 0.
      rs_response = build_error( iv_id = is_message-id iv_code = 'JOB_CLOSE_ERROR' iv_message = |JOB_CLOSE failed, subrc { sy-subrc }| ).
      RETURN.
    ENDIF.

    DATA(lv_o) = '{'.
    DATA(lv_c) = '}'.
    DATA(lv_json) = |{ lv_o }"status":"submitted","report":"{ lv_report }","jobname":"{ lv_jobname }","jobcount":"{ lv_jobcount }"{ lv_c }|.
    rs_response = VALUE #( id = is_message-id success = abap_true data = lv_json ).
  ENDMETHOD.

  METHOD handle_get_job_status.
    DATA: lv_jobname  TYPE tbtcjob-jobname,
          lv_jobcount TYPE tbtcjob-jobcount.

    DATA(lv_jobname_str) = extract_param( iv_params = is_message-params iv_name = 'jobname' ).
    DATA(lv_jobcount_str) = extract_param( iv_params = is_message-params iv_name = 'jobcount' ).

    IF lv_jobname_str IS INITIAL OR lv_jobcount_str IS INITIAL.
      rs_response = build_error( iv_id = is_message-id iv_code = 'MISSING_PARAM' iv_message = 'Parameters jobname and jobcount are required' ).
      RETURN.
    ENDIF.

    TRANSLATE lv_jobname_str TO UPPER CASE.
    lv_jobname = lv_jobname_str.
    lv_jobcount = lv_jobcount_str.

    SELECT SINGLE status FROM tbtco INTO @DATA(lv_status_raw)
      WHERE jobname = @lv_jobname AND jobcount = @lv_jobcount.
    IF sy-subrc <> 0.
      rs_response = build_error( iv_id = is_message-id iv_code = 'JOB_NOT_FOUND' iv_message = |Job { lv_jobname }/{ lv_jobcount } not found| ).
      RETURN.
    ENDIF.

    DATA lv_status TYPE string.
    CASE lv_status_raw.
      WHEN 'P'. lv_status = 'scheduled'.
      WHEN 'S'. lv_status = 'scheduled'.
      WHEN 'Y'. lv_status = 'ready'.
      WHEN 'R'. lv_status = 'running'.
      WHEN 'F'. lv_status = 'finished'.
      WHEN 'A'. lv_status = 'aborted'.
      WHEN OTHERS. lv_status = 'unknown'.
    ENDCASE.

    DATA lv_spools TYPE string.
    SELECT listident FROM tbtcp INTO TABLE @DATA(lt_spool)
      WHERE jobname = @lv_jobname AND jobcount = @lv_jobcount.
    LOOP AT lt_spool INTO DATA(lv_listident).
      DATA(lv_id) = CONV string( lv_listident ).
      CONDENSE lv_id.
      SHIFT lv_id LEFT DELETING LEADING '0'.
      IF lv_id IS INITIAL.
        CONTINUE.
      ENDIF.
      IF lv_spools IS NOT INITIAL.
        lv_spools = |{ lv_spools },|.
      ENDIF.
      lv_spools = |{ lv_spools }"{ lv_id }"|.
    ENDLOOP.

    DATA(lv_o) = '{'.
    DATA(lv_c) = '}'.
    DATA(lv_json) = |{ lv_o }"jobname":"{ lv_jobname }","jobcount":"{ lv_jobcount }","status":"{ lv_status }","spool_ids":[{ lv_spools }]{ lv_c }|.
    rs_response = VALUE #( id = is_message-id success = abap_true data = lv_json ).
  ENDMETHOD.

  METHOD handle_get_spool_output.
    DATA(lv_spool_str) = extract_param( iv_params = is_message-params iv_name = 'spool_id' ).

    IF lv_spool_str IS INITIAL.
      rs_response = build_error( iv_id = is_message-id iv_code = 'MISSING_PARAM' iv_message = 'Parameter spool_id is required' ).
      RETURN.
    ENDIF.

    " Spool functions RABAX inside an ABAP push channel (forbidden statements
    " in SAPLSPOX; DESTINATION-RFC triggers an implicit DB commit, also
    " forbidden). The job's second step ZVSP_SPOOL_XPRT exported the list to
    " INDX; a plain database IMPORT is APC-safe.
    DATA lv_output TYPE string.
    DATA lv_key TYPE indx-srtfd.
    lv_key = |VSPSPOOL_{ lv_spool_str }|.
    IMPORT text = lv_output FROM DATABASE indx(zv) ID lv_key.
    IF sy-subrc <> 0.
      rs_response = build_error( iv_id = is_message-id iv_code = 'SPOOL_NOT_EXPORTED' iv_message = |No exported output for spool { lv_spool_str } - job may still be running or was submitted without the export step| ).
      RETURN.
    ENDIF.

    DATA lt_split TYPE TABLE OF string.
    SPLIT lv_output AT cl_abap_char_utilities=>newline INTO TABLE lt_split.
    DATA(lv_lines) = lines( lt_split ).
    DATA(lv_o) = '{'.
    DATA(lv_c) = '}'.
    DATA(lv_json) = |{ lv_o }"spool_id":"{ lv_spool_str }","lines":{ lv_lines },"output":"{ escape_json( lv_output ) }"{ lv_c }|.
    rs_response = VALUE #( id = is_message-id success = abap_true data = lv_json ).
  ENDMETHOD.

  METHOD handle_get_text_elements.
    DATA: lt_textpool TYPE TABLE OF textpool,
          lv_program  TYPE progname.

    DATA(lv_prog_str) = extract_param( iv_params = is_message-params iv_name = 'program' ).
    DATA(lv_language) = extract_param( iv_params = is_message-params iv_name = 'language' ).

    IF lv_prog_str IS INITIAL.
      rs_response = build_error( iv_id = is_message-id iv_code = 'MISSING_PARAM' iv_message = 'Parameter program is required' ).
      RETURN.
    ENDIF.

    TRANSLATE lv_prog_str TO UPPER CASE.
    lv_program = lv_prog_str.

    DATA lv_lang TYPE sy-langu.
    IF lv_language IS NOT INITIAL.
      lv_lang = lv_language(1).
    ELSE.
      lv_lang = sy-langu.
    ENDIF.

    READ TEXTPOOL lv_program INTO lt_textpool LANGUAGE lv_lang.

    DATA(lv_o) = '{'.
    DATA(lv_c) = '}'.
    DATA lv_json TYPE string.
    lv_json = |{ lv_o }"program":"{ lv_program }","language":"{ lv_lang }","selection_texts":{ lv_o }|.

    DATA lv_first TYPE abap_bool VALUE abap_true.
    DATA lv_entry_str TYPE string.
    LOOP AT lt_textpool INTO DATA(ls_text) WHERE id = 'S'.
      IF lv_first = abap_false.
        lv_json = |{ lv_json },|.
      ENDIF.
      DATA(lv_key) = ls_text-key.
      CONDENSE lv_key.
      " Selection text entry has 8-char key prefix - strip it
      lv_entry_str = ls_text-entry.
      IF strlen( lv_entry_str ) > 8.
        lv_entry_str = lv_entry_str+8.
      ENDIF.
      lv_json = |{ lv_json }"{ lv_key }":"{ escape_json( lv_entry_str ) }"|.
      lv_first = abap_false.
    ENDLOOP.

    lv_json = |{ lv_json }{ lv_c },"text_symbols":{ lv_o }|.

    lv_first = abap_true.
    LOOP AT lt_textpool INTO ls_text WHERE id = 'I'.
      IF lv_first = abap_false.
        lv_json = |{ lv_json },|.
      ENDIF.
      lv_key = ls_text-key.
      CONDENSE lv_key.
      lv_entry_str = ls_text-entry.
      lv_json = |{ lv_json }"{ lv_key }":"{ escape_json( lv_entry_str ) }"|.
      lv_first = abap_false.
    ENDLOOP.

    lv_json = |{ lv_json }{ lv_c }{ lv_c }|.
    rs_response = VALUE #( id = is_message-id success = abap_true data = lv_json ).
  ENDMETHOD.

  METHOD handle_set_text_elements.
    DATA: lt_textpool TYPE TABLE OF textpool,
          lv_program  TYPE progname.

    DATA(lv_prog_str) = extract_param( iv_params = is_message-params iv_name = 'program' ).
    DATA(lv_language) = extract_param( iv_params = is_message-params iv_name = 'language' ).
    DATA(lv_sel_json) = extract_param_object( iv_params = is_message-params iv_name = 'selection_texts' ).
    DATA(lv_sym_json) = extract_param_object( iv_params = is_message-params iv_name = 'text_symbols' ).

    IF lv_prog_str IS INITIAL.
      rs_response = build_error( iv_id = is_message-id iv_code = 'MISSING_PARAM' iv_message = 'Parameter program is required' ).
      RETURN.
    ENDIF.

    TRANSLATE lv_prog_str TO UPPER CASE.
    lv_program = lv_prog_str.

    DATA lv_lang TYPE sy-langu.
    IF lv_language IS NOT INITIAL.
      lv_lang = lv_language(1).
    ELSE.
      lv_lang = sy-langu.
    ENDIF.

    READ TEXTPOOL lv_program INTO lt_textpool LANGUAGE lv_lang.

    DATA lv_sel_count TYPE i.
    DATA lv_sym_count TYPE i.

    IF lv_sel_json IS NOT INITIAL.
      DATA(lv_work) = lv_sel_json.
      WHILE lv_work CS '"'.
        DATA lv_key TYPE string.
        DATA lv_val TYPE string.
        FIND REGEX '"([^"]+)"\s*:\s*"([^"]*)"' IN lv_work SUBMATCHES lv_key lv_val.
        IF sy-subrc = 0.
          TRANSLATE lv_key TO UPPER CASE.
          REPLACE ALL OCCURRENCES OF '\"' IN lv_val WITH '"'.
          REPLACE ALL OCCURRENCES OF '\\' IN lv_val WITH '\'.

          DATA lv_textkey TYPE textpoolky.
          lv_textkey = lv_key.
          " Selection text entry must be: 8-char key prefix + text value
          DATA(lv_entry) = |{ lv_textkey WIDTH = 8 }{ lv_val }|.
          READ TABLE lt_textpool ASSIGNING FIELD-SYMBOL(<fs>) WITH KEY id = 'S' key = lv_textkey.
          IF sy-subrc = 0.
            <fs>-entry = lv_entry.
          ELSE.
            APPEND VALUE textpool( id = 'S' key = lv_textkey entry = lv_entry ) TO lt_textpool.
          ENDIF.
          lv_sel_count = lv_sel_count + 1.

          FIND FIRST OCCURRENCE OF |"{ lv_key }"| IN lv_work MATCH OFFSET DATA(lv_off) MATCH LENGTH DATA(lv_len) IGNORING CASE.
          IF sy-subrc = 0 AND strlen( lv_work ) > lv_off + lv_len.
            lv_work = lv_work+lv_off.
            lv_work = lv_work+lv_len.
          ELSE.
            EXIT.
          ENDIF.
        ELSE.
          EXIT.
        ENDIF.
      ENDWHILE.
    ENDIF.

    IF lv_sym_json IS NOT INITIAL.
      lv_work = lv_sym_json.
      WHILE lv_work CS '"'.
        CLEAR: lv_key, lv_val.
        FIND REGEX '"([^"]+)"\s*:\s*"([^"]*)"' IN lv_work SUBMATCHES lv_key lv_val.
        IF sy-subrc = 0.
          REPLACE ALL OCCURRENCES OF '\"' IN lv_val WITH '"'.
          REPLACE ALL OCCURRENCES OF '\\' IN lv_val WITH '\'.

          lv_textkey = lv_key.
          READ TABLE lt_textpool ASSIGNING <fs> WITH KEY id = 'I' key = lv_textkey.
          IF sy-subrc = 0.
            <fs>-entry = lv_val.
          ELSE.
            APPEND VALUE textpool( id = 'I' key = lv_textkey entry = lv_val ) TO lt_textpool.
          ENDIF.
          lv_sym_count = lv_sym_count + 1.

          FIND FIRST OCCURRENCE OF |"{ lv_key }"| IN lv_work MATCH OFFSET lv_off MATCH LENGTH lv_len.
          IF sy-subrc = 0 AND strlen( lv_work ) > lv_off + lv_len.
            lv_work = lv_work+lv_off.
            lv_work = lv_work+lv_len.
          ELSE.
            EXIT.
          ENDIF.
        ELSE.
          EXIT.
        ENDIF.
      ENDWHILE.
    ENDIF.

    INSERT TEXTPOOL lv_program FROM lt_textpool LANGUAGE lv_lang.

    DATA(lv_o) = '{'.
    DATA(lv_c) = '}'.
    DATA(lv_status) = COND string( WHEN sy-subrc = 0 THEN 'success' ELSE 'error' ).
    DATA lv_json TYPE string.
    lv_json = |{ lv_o }"status":"{ lv_status }","program":"{ lv_program }","language":"{ lv_lang }","selection_texts_set":{ lv_sel_count },"text_symbols_set":{ lv_sym_count }{ lv_c }|.

    rs_response = VALUE #( id = is_message-id success = abap_true data = lv_json ).
  ENDMETHOD.

  METHOD handle_get_variants.
    DATA: lt_varid  TYPE TABLE OF varid,
          lv_report TYPE progname.

    DATA(lv_report_str) = extract_param( iv_params = is_message-params iv_name = 'report' ).

    IF lv_report_str IS INITIAL.
      rs_response = build_error( iv_id = is_message-id iv_code = 'MISSING_PARAM' iv_message = 'Parameter report is required' ).
      RETURN.
    ENDIF.

    TRANSLATE lv_report_str TO UPPER CASE.
    lv_report = lv_report_str.

    SELECT * FROM varid INTO TABLE lt_varid
      WHERE report = lv_report
      ORDER BY variant.

    DATA(lv_o) = '{'.
    DATA(lv_c) = '}'.
    DATA lv_json TYPE string.
    lv_json = |{ lv_o }"report":"{ lv_report }","variants":[|.

    DATA lv_first TYPE abap_bool VALUE abap_true.
    LOOP AT lt_varid INTO DATA(ls_var).
      IF lv_first = abap_false.
        lv_json = |{ lv_json },|.
      ENDIF.
      DATA(lv_protected) = COND string( WHEN ls_var-protected = abap_true THEN 'true' ELSE 'false' ).
      lv_json = |{ lv_json }{ lv_o }"name":"{ ls_var-variant }","protected":{ lv_protected }{ lv_c }|.
      lv_first = abap_false.
    ENDLOOP.

    lv_json = |{ lv_json }]{ lv_c }|.
    rs_response = VALUE #( id = is_message-id success = abap_true data = lv_json ).
  ENDMETHOD.

  METHOD extract_param.
    DATA lv_name TYPE string.
    lv_name = iv_name.
    CONDENSE lv_name.

    DATA lv_search TYPE string.
    lv_search = |"{ lv_name }":|.
    DATA lv_pos TYPE i.
    FIND lv_search IN iv_params MATCH OFFSET lv_pos.
    IF sy-subrc = 0.
      DATA lv_rest TYPE string.
      lv_rest = iv_params+lv_pos.
      FIND REGEX ':\s*"([^"]*)"' IN lv_rest SUBMATCHES rv_value.
    ENDIF.
  ENDMETHOD.

  METHOD extract_param_object.
    DATA lv_name TYPE string.
    lv_name = iv_name.
    CONDENSE lv_name.

    DATA(lv_search) = |"{ lv_name }":|.
    DATA lv_pos TYPE i.
    FIND lv_search IN iv_params MATCH OFFSET lv_pos.
    IF sy-subrc <> 0.
      RETURN.
    ENDIF.

    DATA(lv_rest) = iv_params+lv_pos.
    DATA(lv_brace) = find( val = lv_rest sub = '{' ).
    IF lv_brace < 0.
      RETURN.
    ENDIF.

    DATA lv_depth TYPE i.
    DATA lv_i TYPE i.
    lv_i = lv_brace.
    DATA(lv_len) = strlen( lv_rest ).
    WHILE lv_i < lv_len.
      DATA(lv_char) = lv_rest+lv_i(1).
      IF lv_char = '{'.
        lv_depth = lv_depth + 1.
      ELSEIF lv_char = '}'.
        lv_depth = lv_depth - 1.
        IF lv_depth = 0.
          DATA(lv_obj_len) = lv_i - lv_brace + 1.
          rv_json = lv_rest+lv_brace(lv_obj_len).
          RETURN.
        ENDIF.
      ENDIF.
      lv_i = lv_i + 1.
    ENDWHILE.
  ENDMETHOD.

  METHOD escape_json.
    rv_escaped = iv_string.
    REPLACE ALL OCCURRENCES OF '\' IN rv_escaped WITH '\\'.
    REPLACE ALL OCCURRENCES OF '"' IN rv_escaped WITH '\"'.
    REPLACE ALL OCCURRENCES OF cl_abap_char_utilities=>cr_lf IN rv_escaped WITH '\n'.
    REPLACE ALL OCCURRENCES OF cl_abap_char_utilities=>newline IN rv_escaped WITH '\n'.
    REPLACE ALL OCCURRENCES OF cl_abap_char_utilities=>horizontal_tab IN rv_escaped WITH '\t'.
  ENDMETHOD.

  METHOD build_error.
    DATA(lv_o) = '{'.
    DATA(lv_c) = '}'.
    rs_response = VALUE #(
      id      = iv_id
      success = abap_false
      error   = |{ lv_o }"code":"{ iv_code }","message":"{ escape_json( iv_message ) }"{ lv_c }|
    ).
  ENDMETHOD.

ENDCLASS.

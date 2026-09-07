REPORT zvsp_spool_xprt.

" Runs as step 2 of a ZVSP_* job: exports step 1's ABAP list spool to INDX,
" so the APC WebSocket handler can read it without forbidden statements.
DATA lv_jobname  TYPE tbtcjob-jobname.
DATA lv_jobcount TYPE tbtcjob-jobcount.

CALL FUNCTION 'GET_JOB_RUNTIME_INFO'
  IMPORTING
    jobname         = lv_jobname
    jobcount        = lv_jobcount
  EXCEPTIONS
    no_runtime_info = 1
    OTHERS          = 2.
IF sy-subrc <> 0.
  RETURN.
ENDIF.

SELECT listident FROM tbtcp INTO TABLE @DATA(lt_ids)
  WHERE jobname = @lv_jobname AND jobcount = @lv_jobcount.

LOOP AT lt_ids INTO DATA(lv_listident).
  DATA(lv_id) = CONV string( lv_listident ).
  CONDENSE lv_id.
  SHIFT lv_id LEFT DELETING LEADING '0'.
  IF lv_id IS INITIAL.
    CONTINUE.
  ENDIF.

  DATA lv_rqident TYPE tsp01-rqident.
  lv_rqident = lv_id.
  DATA lt_buffer TYPE TABLE OF soli.
  CALL FUNCTION 'RSPO_RETURN_ABAP_SPOOLJOB'
    EXPORTING
      rqident = lv_rqident
    TABLES
      buffer  = lt_buffer
    EXCEPTIONS
      OTHERS  = 1.
  IF sy-subrc <> 0.
    CONTINUE.
  ENDIF.

  DATA lv_text TYPE string.
  CLEAR lv_text.
  LOOP AT lt_buffer INTO DATA(ls_line).
    IF sy-tabix > 1.
      lv_text = lv_text && cl_abap_char_utilities=>newline.
    ENDIF.
    lv_text = lv_text && |{ ls_line-line }|.
  ENDLOOP.

  DATA lv_key TYPE indx-srtfd.
  lv_key = |VSPSPOOL_{ lv_id }|.
  EXPORT text = lv_text TO DATABASE indx(zv) ID lv_key.
ENDLOOP.

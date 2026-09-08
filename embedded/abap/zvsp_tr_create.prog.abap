REPORT zvsp_tr_create.
" Creates a workbench transport request via the classic CTS function module.
"
" Why a helper: on NetWeaver 7.5x the ADT endpoint POST /sap/bc/adt/cts/transportrequests
" (handler CL_CTS_ADT_TM_REST_RES_CONT->post) does NOT create a request — it only
" handles new_task / consistency_checks / release_jobs, and it reads the action from the
" URI attribute 'traction', not the request body. The tool's ADT create (tm:useraction in
" the body) therefore always fails with "user action  is not supported" (empty action).
" TR_INSERT_REQUEST_WITH_TASKS works on all releases but is not remote-enabled, so it is
" called locally here and the number is returned via the spool.
"
" Deletion works through the tool's normal delete_transport (ADT) — no helper needed.
DATA ls_hdr TYPE trwbo_request_header.
DATA lt_tasks TYPE trwbo_request_headers.
CALL FUNCTION 'TR_INSERT_REQUEST_WITH_TASKS'
  EXPORTING
    iv_type           = 'K'
    iv_text           = 'VSP transport (delete me)'
    iv_owner          = sy-uname
  IMPORTING
    es_request_header = ls_hdr
    et_task_headers   = lt_tasks
  EXCEPTIONS
    enqueue_failed    = 1
    insert_failed     = 2
    OTHERS            = 3.
IF sy-subrc = 0.
  WRITE: / 'TRKORR=', ls_hdr-trkorr.
ELSE.
  WRITE: / 'ERROR subrc=', sy-subrc.
ENDIF.

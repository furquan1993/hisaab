CREATE FUNCTION hisaab.issue_key(issue jsonb) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path='' AS $$
 SELECT (issue->>'code')||':'||coalesce(issue->>'page','')
$$;
CREATE FUNCTION hisaab.critical_issue(code text) RETURNS boolean
LANGUAGE sql IMMUTABLE SET search_path='' AS $$
 SELECT code IN ('date_missing_or_invalid','time_missing_or_invalid','amount_unreadable','amount_missing_or_invalid',
 'direction_ambiguous','direction_missing_or_unknown','currency_unknown','currency_missing_or_unknown',
 'description_missing','entry_type_unknown','entry_type_direction_conflict','statement_date_missing_or_invalid','statement_date_conflict')
$$;
CREATE FUNCTION hisaab.coverage_fingerprint(p_sha text,p_pages integer,p_date date,p_issues jsonb) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path='' AS $$
 SELECT encode(sha256(convert_to(jsonb_build_array(p_sha,p_pages,p_date,p_issues)::text,'UTF8')),'hex')
$$;
CREATE FUNCTION hisaab.effective_values(e hisaab.entries,d hisaab.entry_decisions) RETURNS jsonb
LANGUAGE sql STABLE SET search_path='' AS $$
 SELECT jsonb_build_object('transaction_date',e.transaction_date,'transaction_time',e.transaction_time,
  'description',e.description,'amount',e.amount::text,'direction',e.direction,'currency',e.currency,'entry_type',e.entry_type)
 ||CASE WHEN d.source_fingerprint=hisaab.entry_fingerprint(e) THEN d.overrides::jsonb ELSE '{}'::jsonb END
$$;
CREATE FUNCTION hisaab.unresolved_issues(issues jsonb,values_ jsonb,ack jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE SET search_path='' AS $$
 SELECT coalesce(jsonb_agg(issue ORDER BY position),'[]'::jsonb)
 FROM jsonb_array_elements(issues) WITH ORDINALITY AS x(issue,position)
 WHERE NOT(coalesce(ack,'[]'::jsonb) ? hisaab.issue_key(issue))
 AND NOT CASE issue->>'code'
  WHEN 'date_missing_or_invalid' THEN values_->>'transaction_date' IS NOT NULL
  WHEN 'time_missing_or_invalid' THEN values_->>'transaction_time' IS NOT NULL
  WHEN 'amount_unreadable' THEN values_->>'amount' IS NOT NULL
  WHEN 'amount_missing_or_invalid' THEN values_->>'amount' IS NOT NULL
  WHEN 'direction_ambiguous' THEN values_->>'direction' IS NOT NULL
  WHEN 'direction_missing_or_unknown' THEN values_->>'direction' IS NOT NULL
  WHEN 'currency_unknown' THEN values_->>'currency' IS NOT NULL
  WHEN 'currency_missing_or_unknown' THEN values_->>'currency' IS NOT NULL
  WHEN 'description_missing' THEN length(btrim(coalesce(values_->>'description','')))>0
  WHEN 'entry_type_unknown' THEN coalesce(values_->>'entry_type','unknown')<>'unknown'
  WHEN 'entry_type_direction_conflict' THEN NOT(coalesce(values_->>'entry_type','unknown') IN ('payment','cashback') AND coalesce(values_->>'direction','')<>'credit')
  WHEN 'statement_date_missing_or_invalid' THEN values_->>'statement_date' IS NOT NULL
  WHEN 'statement_date_conflict' THEN values_->>'statement_date' IS NOT NULL AND coalesce((values_->>'statement_date_confirmed')::boolean,false)
  WHEN 'competing_statement_file' THEN coalesce((values_->>'is_selected')::boolean,false)
  WHEN 'ambiguous_statement_match' THEN coalesce((values_->>'is_selected')::boolean,false)
  WHEN 'statement_match_unresolved' THEN coalesce((values_->>'is_selected')::boolean,false)
  ELSE false END
$$;

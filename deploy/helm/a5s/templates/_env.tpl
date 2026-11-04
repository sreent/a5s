{{/* What each part is given, as in deploy/compose.yaml: each reads only its own keys. */}}

{{- define "a5s.env.gateway" -}}
{{ include "a5s.secretEnv" (dict "root" . "name" "A5S_DATABASE_URL" "key" "database-gateway-url") }}
{{ include "a5s.secretEnv" (dict "root" . "name" "A5S_SERVICE_TOKEN" "key" "service-token") }}
{{ include "a5s.secretEnv" (dict "root" . "name" "A5S_SEAL_KEYS" "key" "seal-keys") }}
{{- range $name, $key := .Values.models.keys }}
{{ include "a5s.secretEnv" (dict "root" $ "name" $name "key" $key "optional" true) }}
{{- end }}
- name: A5S_TEAM
  value: {{ .Values.team | quote }}
{{ include "a5s.peopleEnv" . }}
{{- end }}

{{- define "a5s.env.channels" -}}
{{ include "a5s.secretEnv" (dict "root" . "name" "A5S_DATABASE_URL" "key" "database-channels-url") }}
{{ include "a5s.peopleEnv" . }}
{{- end }}

{{- define "a5s.env.scheduler" -}}
{{ include "a5s.secretEnv" (dict "root" . "name" "A5S_DATABASE_URL" "key" "database-scheduler-url") }}
{{ include "a5s.secretEnv" (dict "root" . "name" "A5S_SERVICE_TOKEN" "key" "service-token") }}
- name: A5S_GATEWAY_URL
  value: {{ printf "http://%s-gateway:8700" .Release.Name | quote }}
- name: A5S_WORKER_URL
  value: {{ printf "http://%s-worker:8702" .Release.Name | quote }}
{{- end }}

{{- define "a5s.env.anchor" -}}
{{ include "a5s.secretEnv" (dict "root" . "name" "A5S_DATABASE_URL" "key" "database-anchor-url") }}
- name: A5S_ANCHOR_STORE
  value: {{ required "set anchor.store, where the ledger's locked copies go" .Values.anchor.store | quote }}
- name: A5S_ANCHOR_RETAIN_DAYS
  value: {{ .Values.anchor.retainDays | quote }}
{{- end }}

{{- define "a5s.env.worker" -}}
- name: A5S_GATEWAY_URL
  value: {{ printf "http://%s-gateway:8700" .Release.Name | quote }}
{{- end }}

{{/* The jobs, as the database's administrator. */}}
{{- define "a5s.env.admin" -}}
{{ include "a5s.secretEnv" (dict "root" . "name" "A5S_DATABASE_URL" "key" "database-admin-url") }}
- name: A5S_TEAM
  value: {{ .Values.team | quote }}
{{- end }}

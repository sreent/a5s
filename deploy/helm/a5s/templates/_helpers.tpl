{{/* The image every part runs: a release's, by its digest, or a tag only to try it out. */}}
{{- define "a5s.image" -}}
{{- if .Values.image.digest -}}
{{ .Values.image.repository }}@{{ .Values.image.digest }}
{{- else if .Values.image.tag -}}
{{ .Values.image.repository }}:{{ .Values.image.tag }}
{{- else -}}
{{ fail "set image.digest to a release's image, by its digest, so what runs is what was approved" }}
{{- end -}}
{{- end }}

{{- define "a5s.labels" -}}
app.kubernetes.io/name: a5s
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end }}

{{/* What selects one part's pods: call with (dict "root" $ "part" "gateway"). */}}
{{- define "a5s.selector" -}}
app.kubernetes.io/name: a5s
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .part }}
{{- end }}

{{/* The agents with worker pools of their own, by name, each checked: as JSON, for
fromJsonArray. Each pool's Deployment and Service is named for it, so it must be a name
they can take. */}}
{{- define "a5s.pooled" -}}
{{- $names := keys (.Values.workers.pools | default dict) | sortAlpha }}
{{- range $names }}
{{- if not (regexMatch "^[a-z]([-a-z0-9]{0,38}[a-z0-9])?$" .) }}
{{- fail (printf "workers.pools: %q isn't a name a Deployment can take, such as desk-assistant" .) }}
{{- end }}
{{- end }}
{{- toJson $names }}
{{- end }}

{{/* What selects every worker's pods, in each pool: call with the root. */}}
{{- define "a5s.workersSelector" -}}
matchLabels:
  app.kubernetes.io/name: a5s
  app.kubernetes.io/instance: {{ .Release.Name }}
matchExpressions:
  - key: app.kubernetes.io/component
    operator: In
    values:
      - worker
      {{- range include "a5s.pooled" . | fromJsonArray }}
      - {{ printf "worker-%s" . }}
      {{- end }}
{{- end }}

{{/* Where each agent's own worker pool is, for the scheduler: agent=url, comma-separated. */}}
{{- define "a5s.workerUrls" -}}
{{- $urls := list }}
{{- range include "a5s.pooled" . | fromJsonArray }}
{{- $urls = append $urls (printf "%s=http://%s-worker-%s:8702" . $.Release.Name .) }}
{{- end }}
{{- join "," $urls }}
{{- end }}

{{/* How many of each agent's runs the scheduler works on at once in its pool, for the pools
that say, or whose slots the chart's values set: a5s's default for every other. */}}
{{- define "a5s.workerSlots" -}}
{{- $slots := list }}
{{- range $agent := include "a5s.pooled" . | fromJsonArray }}
{{- $pool := get $.Values.workers.pools $agent | default dict }}
{{- with $pool.slots | default $.Values.workers.slots }}
{{- $slots = append $slots (printf "%s=%v" $agent .) }}
{{- end }}
{{- end }}
{{- join "," $slots }}
{{- end }}

{{/* A part's pods: what selects them, and the rest of the labels, each once. */}}
{{- define "a5s.podLabels" -}}
{{ include "a5s.selector" . }}
app.kubernetes.io/version: {{ .root.Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .root.Chart.Name .root.Chart.Version }}
{{- $extra := get (.root.Values.podLabels | default dict) .part | default dict }}
{{- with omit $extra "app.kubernetes.io/name" "app.kubernetes.io/instance" "app.kubernetes.io/component" "app.kubernetes.io/version" "app.kubernetes.io/managed-by" "helm.sh/chart" }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{/* Each container runs as a5s's own user, with nothing it doesn't need. */}}
{{- define "a5s.securityContext" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
runAsNonRoot: true
runAsUser: 10001
runAsGroup: 10001
capabilities:
  drop: ["ALL"]
seccompProfile:
  type: RuntimeDefault
{{- end }}

{{/* A variable from a key of the Secret. */}}
{{- define "a5s.secretEnv" -}}
- name: {{ .name }}
  valueFrom:
    secretKeyRef:
      name: {{ .root.Values.secret }}
      key: {{ .key }}
      {{- if .optional }}
      optional: true
      {{- end }}
{{- end }}

{{/* How people reach a5s and sign in: for the gateway and the channels. */}}
{{- define "a5s.peopleEnv" -}}
{{- $p := .Values.people -}}
{{- if and $p.oidcIssuer (not $p.oidcMfa) }}
{{- fail "set people.oidcMfa to how your identity provider shows a second factor, such as amr:mfa or acr:<level>, or to none if its tokens show none (docs/first-day.md)" }}
{{- end }}
{{- $mfa := $p.oidcMfa }}{{/* none too, said so: a5s then asks none, and doesn't ask to set it */}}
{{- range $name, $value := dict "A5S_OIDC_ISSUER" $p.oidcIssuer "A5S_OIDC_AUDIENCE" $p.oidcAudience "A5S_OIDC_PERSON_CLAIM" $p.oidcPersonClaim "A5S_OIDC_DIRECTORY_PREFIX" $p.oidcDirectoryPrefix "A5S_OIDC_METADATA_URL" $p.oidcMetadataUrl "A5S_OIDC_MFA" $mfa "A5S_OIDC_GROUPS_CLAIM" $p.oidcGroupsClaim "A5S_WEBCHAT_CLIENT_ID" $p.webchatClientId "A5S_PUBLIC_URL" $p.publicUrl "A5S_MATRIX_HOMESERVER" $.Values.matrix.homeserver "A5S_MATRIX_SERVER_NAME" $.Values.matrix.serverName }}
{{- if $value }}
- name: {{ $name }}
  value: {{ $value | quote }}
{{- end }}
{{- end }}
{{- if .Values.delegation.systems }}
- name: A5S_DELEGATION
  value: {{ include "a5s.delegation" . | quote }}
{{- end }}
{{- if .Values.matrix.homeserver }}
{{ include "a5s.secretEnv" (dict "root" . "name" "A5S_MATRIX_AS_TOKEN" "key" "matrix-as-token") }}
{{ include "a5s.secretEnv" (dict "root" . "name" "A5S_MATRIX_HS_TOKEN" "key" "matrix-hs-token") }}
{{- end }}
{{- if .Values.teams.tenantId }}
- name: A5S_TEAMS_TENANT_ID
  value: {{ .Values.teams.tenantId | quote }}
- name: A5S_TEAMS_BOTS
  value: {{ include "a5s.teamsBots" . | quote }}
{{- range .Values.teams.bots }}
{{ include "a5s.secretEnv" (dict "root" $ "name" (printf "A5S_TEAMS_SECRET_%s" (upper .agent)) "key" (printf "teams-secret-%s" .agent)) }}
{{- end }}
{{- end }}
{{- if .Values.events.sources }}
- name: A5S_EVENT_SOURCES
  value: {{ include "a5s.eventSources" . | quote }}
{{- range .Values.events.sources }}
{{ include "a5s.secretEnv" (dict "root" $ "name" (printf "A5S_EVENT_SECRET_%s" (upper (replace "-" "_" .source))) "key" (printf "event-secret-%s" .source)) }}
{{- end }}
{{- end }}
{{- if .Values.slack.teamId }}
- name: A5S_SLACK_TEAM
  value: {{ .Values.slack.teamId | quote }}
- name: A5S_SLACK_BOTS
  value: {{ include "a5s.slackApps" . | quote }}
{{- range .Values.slack.apps }}
{{ include "a5s.secretEnv" (dict "root" $ "name" (printf "A5S_SLACK_SECRET_%s" (upper .agent)) "key" (printf "slack-secret-%s" .agent)) }}
{{ include "a5s.secretEnv" (dict "root" $ "name" (printf "A5S_SLACK_TOKEN_%s" (upper .agent)) "key" (printf "slack-token-%s" .agent)) }}
{{- end }}
{{- end }}
{{- end }}

{{/* Each system that may send events, as a5s reads them: its name, and the variable its
signing secret is in. */}}
{{- define "a5s.eventSources" -}}
{{- $sources := list -}}
{{- range .Values.events.sources -}}
{{- $sources = append $sources (dict "source" .source "secret_env" (printf "A5S_EVENT_SECRET_%s" (upper (replace "-" "_" .source)))) -}}
{{- end -}}
{{- toJson $sources -}}
{{- end }}

{{/* Each system people may connect their accounts in, as a5s reads them: its endpoints, a5s's
client there, the scopes it asks for, and where the core asks whose account a token is and how
the directory knows it, never its secret. */}}
{{- define "a5s.delegation" -}}
{{- $systems := list -}}
{{- range .Values.delegation.systems -}}
{{- $systems = append $systems (dict "name" .name "title" (.title | default .name) "authorize" .authorize "token" .token "client_id" .clientId "scopes" (.scopes | default list) "whoami" .whoami "whose" .whose "known_as" (.knownAs | default "")) -}}
{{- end -}}
{{- toJson $systems -}}
{{- end }}

{{/* Each agent's Slack app, as a5s reads them: its app id, and the variables its signing
secret and bot token are in. */}}
{{- define "a5s.slackApps" -}}
{{- $apps := list -}}
{{- range .Values.slack.apps -}}
{{- $apps = append $apps (dict "agent" .agent "app_id" .appId "secret_env" (printf "A5S_SLACK_SECRET_%s" (upper .agent)) "token_env" (printf "A5S_SLACK_TOKEN_%s" (upper .agent))) -}}
{{- end -}}
{{- toJson $apps -}}
{{- end }}

{{/* Each agent's bot, as a5s reads them: its app id, and the variable its secret is in. */}}
{{- define "a5s.teamsBots" -}}
{{- $bots := list -}}
{{- range .Values.teams.bots -}}
{{- $bots = append $bots (dict "agent" .agent "app_id" .appId "secret_env" (printf "A5S_TEAMS_SECRET_%s" (upper .agent))) -}}
{{- end -}}
{{- toJson $bots -}}
{{- end }}

{{/* Where a5s writes what it must: nothing else of the image is writable. */}}
{{- define "a5s.scratch" -}}
- name: HOME
  value: /tmp
{{- end }}

{{/* Egress rules the parts' network policies share. */}}

{{- define "a5s.policy.dns" -}}
- to:
    - namespaceSelector: {}
      podSelector:
        matchLabels:
          k8s-app: kube-dns
  ports:
    - {protocol: UDP, port: 53}
    - {protocol: TCP, port: 53}
{{- end }}

{{- define "a5s.policy.telemetry" -}}
{{- $t := .Values.networkPolicies.telemetry -}}
{{- if and .Values.telemetry.endpoint (or $t.podSelector $t.namespaceSelector) }}
- to:
    - {{- with $t.podSelector }}
      podSelector:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with $t.namespaceSelector }}
      namespaceSelector:
        {{- toYaml . | nindent 8 }}
      {{- end }}
  ports:
    - {protocol: TCP, port: {{ $t.port }}}
{{- end }}
{{- end }}

{{- define "a5s.policy.database" -}}
{{- $db := .Values.networkPolicies.database -}}
- to:
    {{- range $db.cidrs }}
    - ipBlock:
        cidr: {{ . }}
    {{- end }}
    {{- if or $db.podSelector $db.namespaceSelector }}
    - {{- with $db.podSelector }}
      podSelector:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with $db.namespaceSelector }}
      namespaceSelector:
        {{- toYaml . | nindent 8 }}
      {{- end }}
    {{- end }}
    {{- if not (or $db.cidrs $db.podSelector $db.namespaceSelector) }}
    {{- fail "set networkPolicies.database to where Postgres is: its pods' labels, or its addresses" }}
    {{- end }}
  ports:
    - {protocol: TCP, port: {{ $db.port }}}
{{- end }}

{{- define "a5s.policy.outside" -}}
- to:
    {{- range .Values.networkPolicies.outside }}
    - ipBlock:
        cidr: {{ . }}
    {{- end }}
{{- end }}

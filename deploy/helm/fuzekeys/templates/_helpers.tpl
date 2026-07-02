{{/* Common naming helpers */}}
{{- define "fuzekeys.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "fuzekeys.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "fuzekeys.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Standard labels */}}
{{- define "fuzekeys.labels" -}}
helm.sh/chart: {{ include "fuzekeys.chart" . }}
app.kubernetes.io/name: {{ include "fuzekeys.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: fuzekeys
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
fuzekeys.io/environment: {{ .Values.global.environment }}
{{- end -}}

{{/* Per-component selector labels. Call as (dict "ctx" . "component" "backend") */}}
{{- define "fuzekeys.selectorLabels" -}}
app.kubernetes.io/name: {{ include "fuzekeys.name" .ctx }}
app.kubernetes.io/instance: {{ .ctx.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{/*
  Resolve a component image as <registry>/<repository>:<tag>.
  `comp.image.repository` (if set) must be a BARE path with NO registry host —
  the registry is always prefixed here, so including it would double-prefix.
  Default repository is <global.imageRepository>/<default-basename>.
*/}}
{{- define "fuzekeys.image" -}}
{{- $ctx := .ctx -}}
{{- $comp := .comp -}}        {{/* component values block */}}
{{- $default := .default -}}  {{/* default image basename, e.g. "backend" */}}
{{- $reg := $ctx.Values.global.imageRegistry -}}
{{- $repo := default (printf "%s/%s" $ctx.Values.global.imageRepository $default) $comp.image.repository -}}
{{- $tag := default $ctx.Chart.AppVersion $comp.image.tag -}}
{{- printf "%s/%s:%s" $reg $repo $tag -}}
{{- end -}}

{{/* ServiceAccount name */}}
{{- define "fuzekeys.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "fuzekeys.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/* Build a FuzeInfra host: namespaced FQDN when useNamespacedDns, else raw host */}}
{{- define "fuzekeys.fuzeHost" -}}
{{- $ctx := .ctx -}}
{{- $host := .host -}}
{{- if $ctx.Values.fuzeinfra.useNamespacedDns -}}
{{- printf "%s.%s.svc.cluster.local" $host $ctx.Values.fuzeinfra.namespace -}}
{{- else -}}
{{- $host -}}
{{- end -}}
{{- end -}}

{{/*
  Node affinity block: on the shared cluster, app pods pin to the workload node
  via the `node-role=<global.nodeRole>` label (set by the deploy/terraform node
  request with role=workload). Empty nodeRole (local/kind) renders nothing.
  Call as (include "fuzekeys.nodeSelector" .) — emits a `nodeSelector:` block.
*/}}
{{- define "fuzekeys.nodeSelector" -}}
{{- if .Values.global.nodeRole }}
nodeSelector:
  node-role: {{ .Values.global.nodeRole | quote }}
{{- end }}
{{- end -}}

{{/* Secret name to reference (existing SealedSecret-provided one, or chart-managed fallback) */}}
{{- define "fuzekeys.secretName" -}}
{{- if .Values.secrets.existingSecret -}}
{{- .Values.secrets.existingSecret -}}
{{- else -}}
{{- printf "%s-secrets" (include "fuzekeys.fullname" .) -}}
{{- end -}}
{{- end -}}

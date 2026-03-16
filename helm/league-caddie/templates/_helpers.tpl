{{/*
_helpers.tpl — Named template fragments shared across all chart templates.

Usage examples:
  name:      {{ include "league-caddie.fullname" . }}
  labels:    {{ include "league-caddie.labels" . | nindent 4 }}
  image:     {{ include "league-caddie.image" (dict "root" . "repo" .Values.api.image.repository) }}
*/}}

{{/* Chart name (truncated to 63 chars — Kubernetes label limit). */}}
{{- define "league-caddie.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Fully-qualified release name: "<release>-<chart>" (max 63 chars).
Used as the base for all Kubernetes resource names so that two installs
in the same namespace (e.g. dev + prod) never collide.
*/}}
{{- define "league-caddie.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/* Chart label: "<name>-<version>". */}}
{{- define "league-caddie.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Standard Kubernetes labels applied to every resource.
Follows the recommended label schema:
  https://kubernetes.io/docs/concepts/overview/working-with-objects/common-labels/
*/}}
{{- define "league-caddie.labels" -}}
helm.sh/chart: {{ include "league-caddie.chart" . }}
{{ include "league-caddie.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels — used in matchLabels and pod template labels.
Must be stable (never change after first deploy) because Deployments
use them to find their pods.
*/}}
{{- define "league-caddie.selectorLabels" -}}
app.kubernetes.io/name: {{ include "league-caddie.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Resolve the full Docker image reference for a service.

Call with a dict:
  {{ include "league-caddie.image" (dict "root" . "repo" .Values.api.image.repository) }}

Produces:
  - "<registry>/<repo>:<tag>"  when registry is set
  - "<repo>:<tag>"             otherwise (local dev / CI before ECR push)
*/}}
{{- define "league-caddie.image" -}}
{{- $root := .root }}
{{- $repo := .repo }}
{{- $tag  := $root.Values.image.tag | default "latest" }}
{{- if $root.Values.image.registry }}
{{- printf "%s/%s:%s" $root.Values.image.registry $repo $tag }}
{{- else }}
{{- printf "%s:%s" $repo $tag }}
{{- end }}
{{- end }}

{{/*
Name of the ConfigMap holding non-secret environment variables.
*/}}
{{- define "league-caddie.configmapName" -}}
{{- printf "%s-config" (include "league-caddie.fullname" .) }}
{{- end }}

{{/*
Name of the Secret holding sensitive environment variables.
*/}}
{{- define "league-caddie.secretName" -}}
{{- printf "%s-secret" (include "league-caddie.fullname" .) }}
{{- end }}

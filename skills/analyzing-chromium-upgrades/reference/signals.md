# Interpreting signals, buckets and scores

A signal is a label assigned by the comparison code. It describes a recorded
declaration change or the classifier's interpretation of it. It is not a
measurement of product behaviour, deployment or user impact. Read `before`,
`after` and `deltas` first, then verify relevant source and consumers.

This reference covers signal identifiers, not feature names to search for.
A finding without a signal still needs analysis. Source changes not parsed
into findings must be inspected separately.

## Feature declarations and conditions

| Signal | Recorded change or classification | Additional evidence needed |
|---|---|---|
| `enabled_by_default` / `disabled_by_default` | The feature default changed for Windows | Runtime overrides and the affected code path |
| `default_flip_on` / `default_flip_off` | The general declaration default changed | Whether the Windows branch changed; whether this was a revert requires history |
| `new_feature_on_by_default` | A new feature has an enabled Windows source default | Consumers and actual product availability |
| `flag_retired_on` / `flag_retired_off` | A feature declaration disappeared after an enabled/disabled default | Whether its implementation was retained, removed or replaced |
| `feature_deleted` | A feature declaration disappeared and its prior state was not determined | Earlier declaration, replacement and consumers |
| `feature_string_renamed` | The external feature string changed | Configurations using the old string and any compatibility handling |
| `feature_symbol_renamed` | The C++ identifier changed while the feature string remained | Code referring to the old identifier |
| `build_gate_changed` | Recorded build conditions changed | The relevant build configuration and all declaration locations |
| `declaration_moved` | The declaration was matched at another path | Consumers and surrounding conditions; movement alone does not establish unchanged behaviour |

`platform_state.windows` is the tool's interpretation of source conditions.
`conditional` means those conditions cannot be fully resolved for this
comparison. Neither an enabled default nor a removed flag proves the actual
Finch configuration or permanent product behaviour.

## Blink runtime declarations and Web IDL

| Signal | Recorded change or classification | Additional evidence needed |
|---|---|---|
| `web_api_shipped` | A runtime declaration was added as stable or changed to stable for the recorded platform | API declarations, exposure, remaining conditions and deployment evidence |
| `web_api_unshipped` | The recorded runtime status changed from stable to a lower status | Consumers, other enablement paths and history |
| `killswitch_retired` | A runtime declaration disappeared after a stable status | Whether API declarations and implementation remain |
| `experimental_dropped` | A runtime declaration disappeared and its last recorded status was not stable | Actual prior exposure and whether implementation was removed or replaced |
| `web_api_added_live` | The classifier evaluated an added IDL declaration as callable under the recorded conditions | Interface conditions, exposure, secure-context requirements and actual runtime configuration |
| `web_api_added_gated` | The classifier treated an added IDL declaration's recorded runtime condition as not enabled by default | Other enablement paths; this does not prove that no context can use it |
| `web_api_added` | An API/runtime declaration was added without a resolved stable-availability conclusion | Check the finding kind, runtime declaration and missing conditions |
| `web_api_removed` | An IDL declaration disappeared and the classifier did not determine that its prior conditions disabled access | Absence coverage, replacements and affected consumers; availability may be unresolved |
| `web_api_removed_gated` | An IDL declaration disappeared and the classifier evaluated its prior recorded runtime condition as disabling access | Whether any relevant context enabled it |
| `web_api_overload_removed` | One or more extracted method signatures disappeared | Calls using those signatures and available replacements |
| `web_api_overload_added` | Signatures were added without the classifier detecting an argument-count conflict | Type conversion, overload selection and existing callers |
| `web_api_overload_shadowed` | Added signatures may change selection by argument count, including previously excess arguments | Full overload rules and representative calls |
| `web_api_signature_change` | A member signature or member type changed | Callers, conversion rules and runtime conditions |
| `web_api_shape_changed` | Interface inheritance, declaration kind or enum values changed | Inherited members and consumers |
| `web_api_exposure_changed` | Extended attributes or recorded member runtime conditions changed | The complete conditions on both member and interface |
| `web_api_status_moved` | Runtime status changed without entering or leaving stable | Contexts where those statuses or overrides apply |
| `origin_trial_change` | Origin-trial configuration changed | Applicable origins, platform, token and other runtime requirements |
| `runtime_flag_rewired` | Dependencies, base-feature association or other runtime metadata changed | Compare the changed fields and code using them |

A stable runtime status is not sufficient evidence that every page can call
an API. A non-stable status is not evidence that every context is unable to
call it. A new member can have conditions inherited from its interface.
`base_feature: none` means no generated base-feature association is declared;
it does not establish that an independently declared C++ feature was removed.

## Mojo IPC declarations

IPC means communication between processes. These signals describe interface
declarations, not observed communication failures.

| Signal | Recorded change or classification | Additional evidence needed |
|---|---|---|
| `ipc_signature_change` | Method parameters or response changed | Callers, implementations and whether both sides use matching generated bindings |
| `ipc_ordinal_changed` | A method's explicit ordinal or compared stable position changed | Generated message identifiers and relevant version combinations |
| `ipc_shape_changed` | Field type/ordinal, compared stable position or container kind changed | Generated serialization and consumers |
| `ipc_enum_changed` | Enum values or their recorded annotations changed | Extensibility, defaults and handling of unknown values |
| `ipc_removed` | A Mojo declaration disappeared from the compared facts | Absence coverage, replacements and consumers |
| `ipc_stability_changed` | The recorded `[Stable]` annotation changed | Compatibility requirements; this alone does not describe changed bytes |
| `ipc_field_annotated` | Field default or version annotation changed | Generated defaults and compatibility behaviour for the relevant peers |

For an enum, inspect attributes such as `[Extensible]` and `[Default]` before
describing unknown-value handling. Do not assume every peer rejects unknown
values or every signature change causes a runtime failure. See sections 10
and 13 of [traps.md](traps.md).

## Preferences, switches, parameters and WebUI

| Signal | Recorded change or classification | Additional evidence needed |
|---|---|---|
| `pref_renamed` / `switch_renamed` | Entries were paired as a possible persisted-key or switch rename | Confirm the relationship, consumers and compatibility handling |
| `pref_symbol_renamed` / `switch_symbol_renamed` | The source identifier changed while the string remained | Source consumers using the old identifier |
| `pref_left_scan` / `switch_left_scan` | The key is no longer present in files this run examined | Search for movement, replacement and migration in sufficiently complete source |
| `param_removed` | A feature parameter declaration disappeared | Readers, replacements and external configurations |
| `param_rewired` | A parameter's recorded type or owning feature changed | Readers and the conditions of the new owner |
| `param_default_changed` | A parameter default changed | Consumers and overrides |
| `ui_page_added` / `ui_page_removed` | A route declaration appeared or disappeared | Route conditions, alternative routes and page behaviour |
| `ui_page_regated` | Recorded route conditions changed | Full expressions and values supplied by the C++ handler |
| `ui_page_moved` | A route path or parent changed | Navigation consumers and any redirects |
| `ui_control_added` / `ui_control_removed` | An extracted control appeared or disappeared | Alternative controls, template conditions and event handling |
| `ui_control_type_changed` | The element type changed | Control behaviour and value representation |
| `ui_control_repointed` | A control's preference binding changed | Both preference keys, readers and migration |
| `ui_control_relabelled` | A label resource key changed | Actual localized strings; key changes do not prove visible text changes |
| `ui_gate_added` / `ui_gate_removed` / `ui_gate_changed` | A handler's recorded visibility expression changed | All terms in the expression and the code using its value |
| `flag_expiring` / `flag_expiry_moved` | Flag-entry expiry metadata was scheduled or changed | Exact milestone and whether removal occurred; scheduling is not removal |

## Buckets and scores

Buckets organize the raw report. They are not the headings for the final
event report and do not prove product consequences.

| Bucket | How to use it during analysis |
|---|---|
| Compatibility break | Inspect possible contract changes and identify actual affected consumers |
| Behaviour change | Determine whether the declaration change alters behaviour under the relevant conditions |
| New declarations | Investigate possible new capabilities and their conditions; a declaration alone does not prove availability |
| Scheduled | Check future work recorded in metadata; distinguish plans from completed changes |
| Upstream cleanup | Verify whether changes are non-behavioural, platform-excluded or based on incomplete absence evidence |

The leading signal determines the finding's severity and bucket. Without
signals, the classifier uses the finding kind and direction. The score then
accounts for recorded platform exclusion and incomplete absence evidence.
These numbers are priorities, not probabilities, confidence levels or
measured user impact. Read `reasons` to understand a deduction.

`unconfirmed` is separate from bucket and score. It means the comparison
lacks sufficient absence evidence; it is not a probability that the finding
is wrong. A wider scan may improve file coverage but cannot establish
complete parsing or complete behavioural coverage.

Do not change ranking constants as part of analyzing a user's upgrade.
Explain any disagreement with a classifier label using the actual evidence.

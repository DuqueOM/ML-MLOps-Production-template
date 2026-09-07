# Release Checklist

## Required Checks

1. Confirm `CHANGELOG.md` has the release entry and breaking/adopter notes.
2. Confirm `releases/vX.Y.Z.md` exists and links back to the changelog.
3. Run the template validators and scaffold smoke applicable to the release.
4. Confirm no unreplaced `{ServiceName}`, `{service}`, `{service-name}`, or `{SERVICE}` placeholders leak into rendered
   output.
5. Confirm cloud deploy docs state which validations are local versus external.

## Approval

Release approval is CONSULT for pre-GA releases and STOP for GA or production-claiming releases.

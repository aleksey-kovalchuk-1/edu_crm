import { Modal } from "../Modal";
import { LaunchForm } from "./LaunchForm";
import { UniversityForm } from "./UniversityForm";

export type CreateKind = "university" | "launch";

export function CreateModal({
  kind,
  close,
}: {
  kind: CreateKind;
  close: () => void;
}) {
  return (
    <Modal
      title={
        kind === "university" ? "Новое учебное заведение" : "Новое взаимодействие"
      }
      close={close}
    >
      {kind === "university" ? (
        <UniversityForm onDone={close} />
      ) : (
        <LaunchForm onDone={close} />
      )}
    </Modal>
  );
}

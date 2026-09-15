import type { CreateKind } from "../../app/navigation";
import { Modal } from "../Modal";
import { ContractForm } from "./ContractForm";
import { LaunchForm } from "./LaunchForm";
import { UniversityForm } from "./UniversityForm";

export type { CreateKind };

const TITLES: Record<CreateKind, string> = {
  university: "Новое учебное заведение",
  launch: "Новое взаимодействие",
  contract: "Новый договор",
};

export function CreateModal({
  kind,
  close,
}: {
  kind: CreateKind;
  close: () => void;
}) {
  return (
    <Modal title={TITLES[kind]} close={close} wide={kind === "contract"}>
      {kind === "university" && <UniversityForm onDone={close} />}
      {kind === "launch" && <LaunchForm onDone={close} />}
      {kind === "contract" && <ContractForm onDone={close} />}
    </Modal>
  );
}

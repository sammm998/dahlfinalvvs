import GoldenPanel from "../components/GoldenPanel";
import { t as tr } from "../i18n";

/* Kundens radiatorlista korsad mot Altech enligt Golden Standard, utan ritning. */
export default function RadiatorListPage() {
  return (
    <main>
      <h1>{tr("Radiatorlista till Altech och Prixel")}</h1>
      <GoldenPanel />
    </main>
  );
}

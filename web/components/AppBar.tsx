import Link from "next/link";
import { NAME } from "@/shared/brand";
import { Logo } from "@/shared/icons";

export function AppBar() {
  return (
    <header className="appbar">
      <Link className="brand" href="/" aria-label={`${NAME} home`}>
        <Logo />
        {NAME}
      </Link>
      <nav className="meta" style={{ display: "flex", gap: 6, alignItems: "center" }} aria-label="Main">
        <Link className="btn q sm" href="/">
          Overview
        </Link>
        <Link className="btn sm" href="/map">
          Map
        </Link>
      </nav>
    </header>
  );
}

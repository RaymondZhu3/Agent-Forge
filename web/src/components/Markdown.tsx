import { ExternalLink } from "lucide-react";
import { Fragment, createContext, useContext, type ReactNode } from "react";
import { hostOf } from "../lib/format";

/* Small purpose-built markdown renderer for agent answers (headings, nested lists, bold/italic/code, links).
   No raw HTML is ever injected: everything is rendered as React nodes. */

type Block =
  | { t: "h"; level: number; text: string }
  | { t: "p"; text: string }
  | { t: "hr" }
  | { t: "list"; ordered: boolean; items: Item[] };
type Item = { text: string; children: Block[] };

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^)\s]+\)|https?:\/\/[^\s)\]]+|\*[^*\s][^*]*\*)/g;

/** Fact-check result per figure as written ("$199.00" -> false). When provided, figures in the text are marked. */
export const FigureMarks = createContext<Map<string, boolean> | null>(null);
const FIGURE = /\$\s?\d{1,3}(?:,\d{3})+(?:\.\d+)?|\$\s?\d+(?:\.\d+)?|(?<![\w.])\d+(?:\.\d+)?\s?%/g;

function Figures({ text }: { text: string }) {
  const marks = useContext(FigureMarks);
  if (!marks || !marks.size) return <>{text}</>;
  const out: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(FIGURE)) {
    const ok = marks.get(m[0].trim());
    if (ok === undefined) continue;
    if (m.index! > last) out.push(text.slice(last, m.index));
    out.push(
      <span key={m.index} className={`fig ${ok ? "v" : "u"}`} title={ok ? "Matches the data a tool returned" : "No tool returned this figure"}>
        {m[0]}
        {!ok && <span className="sr"> (no tool returned this figure)</span>}
      </span>,
    );
    last = m.index! + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return <>{out}</>;
}

export function renderInline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  const inlineRe = new RegExp(INLINE.source, "g"); // per call: recursive calls must not share lastIndex
  while ((m = inlineRe.exec(text))) {
    if (m.index > last) out.push(<Figures key={`t${i}`} text={text.slice(last, m.index)} />);
    const tok = m[0];
    const key = i++;
    if (tok.startsWith("**")) out.push(<strong key={key}>{renderInline(tok.slice(2, -2))}</strong>);
    else if (tok.startsWith("`")) out.push(<code key={key}>{tok.slice(1, -1)}</code>);
    else if (tok.startsWith("[")) {
      const mm = /^\[([^\]]+)\]\((.+)\)$/.exec(tok)!;
      out.push(<SourceLink key={key} href={mm[2]} label={mm[1]} />);
    } else if (tok.startsWith("http")) {
      const url = tok.replace(/[.,;]+$/, "");
      out.push(<SourceLink key={key} href={url} label={hostOf(url)} />);
      if (url.length < tok.length) out.push(tok.slice(url.length));
    } else out.push(<em key={key}>{tok.slice(1, -1)}</em>);
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(<Figures key="tail" text={text.slice(last)} />);
  return out;
}

function SourceLink({ href, label }: { href: string; label: string }) {
  return (
    <a className="src-link" href={href} target="_blank" rel="noopener noreferrer">
      {label.startsWith("http") ? hostOf(label) : label}
      <ExternalLink size={11} />
    </a>
  );
}

const bulletRe = /^(\s*)([*\-+]|\d+[.)])\s+(.*)$/;

export function parse(src: string): Block[] {
  const lines = src.replace(/\r/g, "").split("\n");
  const root: Block[] = [];
  let i = 0;

  const parseList = (indent: number): Block => {
    const first = bulletRe.exec(lines[i])!;
    const ordered = /\d/.test(first[2]);
    const items: Item[] = [];
    while (i < lines.length) {
      const m = bulletRe.exec(lines[i]);
      if (!m) break;
      const ind = m[1].length;
      if (ind < indent) break;
      if (ind > indent) {
        // nested list belongs to previous item
        const prev = items[items.length - 1];
        if (!prev) break;
        prev.children.push(parseList(ind));
        continue;
      }
      items.push({ text: m[3], children: [] });
      i++;
      // continuation lines (indented plain text)
      while (i < lines.length && lines[i].trim() && !bulletRe.test(lines[i]) && /^\s{2,}/.test(lines[i])) {
        items[items.length - 1].text += " " + lines[i].trim();
        i++;
      }
    }
    return { t: "list", ordered, items };
  };

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      root.push({ t: "h", level: h[1].length, text: h[2] });
      i++;
    } else if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      root.push({ t: "hr" });
      i++;
    } else if (bulletRe.test(line)) {
      root.push(parseList(bulletRe.exec(line)![1].length));
    } else {
      const buf: string[] = [];
      while (i < lines.length && lines[i].trim() && !/^(#{1,4})\s/.test(lines[i]) && !bulletRe.test(lines[i]) && !/^\s*(-{3,}|\*{3,})\s*$/.test(lines[i])) {
        buf.push(lines[i].trim());
        i++;
      }
      root.push({ t: "p", text: buf.join(" ") });
    }
  }
  return root;
}

function Blocks({ blocks }: { blocks: Block[] }) {
  return (
    <>
      {blocks.map((b, i) => {
        switch (b.t) {
          case "h":
            return b.level <= 2 ? <h3 key={i}>{renderInline(b.text)}</h3> : <h4 key={i}>{renderInline(b.text)}</h4>;
          case "hr":
            return <hr key={i} />;
          case "p":
            return <p key={i}>{renderInline(b.text)}</p>;
          case "list": {
            const Tag = b.ordered ? "ol" : "ul";
            return (
              <Tag key={i}>
                {b.items.map((it, j) => (
                  <li key={j}>
                    {renderInline(it.text)}
                    <Blocks blocks={it.children} />
                  </li>
                ))}
              </Tag>
            );
          }
        }
      })}
    </>
  );
}

/** Splits an answer at its section headings so each section can be shown as its own card. */
export function splitSections(src: string): { intro: Block[]; sections: { title: string; blocks: Block[] }[]; outro: Block[] } {
  const blocks = parse(src).filter((b) => b.t !== "hr");
  const intro: Block[] = [];
  const sections: { title: string; blocks: Block[] }[] = [];
  for (const b of blocks) {
    if (b.t === "h") sections.push({ title: b.text, blocks: [] });
    else if (sections.length) sections[sections.length - 1].blocks.push(b);
    else intro.push(b);
  }
  return { intro, sections, outro: [] };
}


/* ---------- editorial story cards (News Monitor) ----------
   A story is a top-level bullet whose sub-bullets look like "**Label:** value". */

type Story = { title: string; fields: { label: string; value: string }[] };
const fieldRe = /^\*\*([^*]{1,40}?):?\*\*:?\s*(.*)$/;

export function extractStories(blocks: Block[]): { before: Block[]; stories: Story[]; after: Block[] } | null {
  const stories: Story[] = [];
  const before: Block[] = [];
  const after: Block[] = [];
  for (const b of blocks) {
    if (b.t === "list") {
      const found = b.items.map((it) => {
        const kids = it.children.flatMap((c) => (c.t === "list" ? c.items : []));
        const fields = kids.map((k) => fieldRe.exec(k.text)).filter(Boolean).map((m) => ({ label: m![1].replace(/:$/, ""), value: m![2] }));
        return fields.length >= 2 ? { title: it.text.replace(/^\*\*(.+)\*\*$/, "$1"), fields } : null;
      });
      if (found.some(Boolean)) {
        found.forEach((f) => f && stories.push(f));
        continue;
      }
    }
    (stories.length ? after : before).push(b);
  }
  return stories.length >= 1 ? { before, stories, after } : null;
}

const firstUrl = (v: string): string | null => /\((https?:\/\/[^)\s]+)\)/.exec(v)?.[1] ?? /(https?:\/\/[^\s)]+)/.exec(v)?.[0] ?? null;

function StoryCard({ story, index }: { story: Story; index: number }) {
  const get = (k: RegExp) => story.fields.find((f) => k.test(f.label.toLowerCase()));
  const source = get(/^source/), date = get(/^date|publish/), link = get(/^(url|link)/);
  const rest = story.fields.filter((f) => f !== source && f !== date && f !== link);
  const url = link ? firstUrl(link.value) : null;
  return (
    <article className="story">
      <div className="story-meta mono">
        <span className="idx">{String(index + 1).padStart(2, "0")}</span>
        {source && <span>{source.value.replace(/\*\*/g, "")}</span>}
        {date && <span className="dim">{date.value}</span>}
      </div>
      <h3>{renderInline(story.title)}</h3>
      {rest.map((f) => (
        <p key={f.label} className={/matter|why|summary/i.test(f.label) ? "story-why" : ""}>
          {!/matter|why|summary/i.test(f.label) && <strong>{f.label}: </strong>}
          {renderInline(f.value)}
        </p>
      ))}
      {url && (
        <a className="story-link" href={url} target="_blank" rel="noopener noreferrer">
          Read original{source ? ` on ${source.value.replace(/\*\*/g, "")}` : ""} <ExternalLink size={12} />
        </a>
      )}
    </article>
  );
}

export function MarkdownBlocks({ blocks }: { blocks: Block[] }) {
  return (
    <div className="md">
      <Blocks blocks={blocks} />
    </div>
  );
}

export default function Markdown({ text, cards = false, stories = false }: { text: string; cards?: boolean; stories?: boolean }) {
  if (stories) {
    const ex = extractStories(parse(text).filter((b) => b.t !== "hr"));
    if (ex)
      return (
        <div className="md">
          {ex.before.length > 0 && <Blocks blocks={ex.before} />}
          <div className="stories">{ex.stories.map((st, i) => <StoryCard key={i} story={st} index={i} />)}</div>
          {ex.after.length > 0 && <Blocks blocks={ex.after} />}
        </div>
      );
  }
  if (!cards) return <MarkdownBlocks blocks={parse(text)} />;
  const { intro, sections } = splitSections(text);
  if (sections.length < 2) return <MarkdownBlocks blocks={parse(text)} />;
  return (
    <div className="md">
      {intro.length > 0 && <Blocks blocks={intro} />}
      <div className="answer-cards">
        {sections.map((s, i) => (
          <Fragment key={i}>
            <section className="answer-card">
              <header>
                <span className="idx">{String(i + 1).padStart(2, "0")}</span>
                <h3>{renderInline(s.title.replace(/^\d+[.)]\s*/, ""))}</h3>
              </header>
              <Blocks blocks={s.blocks} />
            </section>
          </Fragment>
        ))}
      </div>
    </div>
  );
}

import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { TranscriptBuffer } from "../src/lib/speech";

const say = (...texts: string[]) => texts.map((text) => ({ text, isFinal: true }));

describe("TranscriptBuffer", () => {
  it("returns only what was said since the previous take", () => {
    const b = new TranscriptBuffer();
    b.update(say("help", "there is smoke"));
    expect(b.take()).toBe("help there is smoke");
    expect(b.take()).toBe("");
    b.update(say("help", "there is smoke", "I am hurt"));
    expect(b.take()).toBe("I am hurt");
  });

  it("includes interim words once, in the chunk where they first appear", () => {
    const b = new TranscriptBuffer();
    b.update([{ text: "the kitchen is on", isFinal: false }]);
    expect(b.take()).toBe("the kitchen is on");
    // The recognizer later finalizes that same result; it must not be repeated.
    b.update([{ text: "the kitchen is on fire", isFinal: true }]);
    expect(b.take()).toBe("");
  });

  it("keeps unread words when the recognizer restarts", () => {
    const b = new TranscriptBuffer();
    b.update(say("fire in the kitchen"));
    b.restart();
    b.update(say("please hurry"));
    expect(b.take()).toBe("fire in the kitchen please hurry");
  });

  it("does not repeat words already read before a restart", () => {
    const b = new TranscriptBuffer();
    b.update(say("fire"));
    expect(b.take()).toBe("fire");
    b.restart();
    b.update(say("hurry"));
    expect(b.take()).toBe("hurry");
  });

  it("trims whitespace and skips empty results", () => {
    const b = new TranscriptBuffer();
    b.update(say("  help ", "", "  "));
    expect(b.take()).toBe("help");
  });

  it("property: every spoken phrase is returned exactly once, in order", () => {
    type Op = { kind: "speak"; word: string } | { kind: "take" } | { kind: "restart" };
    const word = fc.stringMatching(/^[a-z]{1,8}$/);
    const op: fc.Arbitrary<Op> = fc.oneof(
      { weight: 5, arbitrary: word.map((w): Op => ({ kind: "speak", word: w })) },
      { weight: 2, arbitrary: fc.constant<Op>({ kind: "take" }) },
      { weight: 1, arbitrary: fc.constant<Op>({ kind: "restart" }) },
    );
    fc.assert(
      fc.property(fc.array(op, { maxLength: 40 }), (ops) => {
        const b = new TranscriptBuffer();
        let current: string[] = []; // results of the current recognizer session
        const spoken: string[] = [];
        const taken: string[] = [];
        for (const o of ops) {
          if (o.kind === "speak") {
            current = [...current, o.word];
            spoken.push(o.word);
            b.update(say(...current));
          } else if (o.kind === "restart") {
            current = [];
            b.restart();
          } else {
            taken.push(b.take());
          }
        }
        taken.push(b.take());
        expect(taken.join(" ").split(" ").filter(Boolean)).toEqual(spoken);
      }),
    );
  });
});
